import re
import os
import urlparse
import urllib
import urllib2
import logging
import json
import requests
from ckanext.datapreview.transform.base import transformer
from ckanext.datapreview.lib.errors import (ResourceError, RequestError)

log = logging.getLogger('ckanext.datapreview.lib.helpers')

REDIRECT_LIMIT = 3

def get_resource_format_from_qa(resource):
    '''Returns the format of the resource, as detected by QA.
    If there is none recorded for this resource, returns None
    '''
    import ckan.model as model
    task_status = model.Session.query(model.TaskStatus).\
                  filter(model.TaskStatus.task_type=='qa').\
                  filter(model.TaskStatus.key=='status').\
                  filter(model.TaskStatus.entity_id==resource.id).first()
    if not task_status:
        return None

    try:
        status = json.loads(task_status.error)
    except ValueError:
        return {}
    return status['format']

def get_resource_length(url, resource, required=False, redirects=0):
    '''Get file size of a resource.

    Either do a HEAD request to the url, or checking the
    size on disk.

    :param url: URL to check
    :param resource: Resource object, just for identification purposes
    :param required: ?
    :param redirects: For counting the number of recursions due to redirects

    On error, this method raises ResourceError.

    If the headers do not contain the length, this method returns None.
    '''
    log.debug('Getting resource length of %s' % url)
    if not url.startswith('http'):
        try:
            if not os.path.exists(url):
                raise ResourceError("Unable to access resource",
                    "The resource was not found in the resource cache: %s" % \
                                    identify_resource(resource))
        except:
            # If the URL is neither http:// or a valid path then we should just log the
            # error
            log.info(u"Unable to check existence of the resource: {0}".format(url))
            raise ResourceError("Unable to access resource",
                "The resource was not found in the resource cache: %s" % \
                                    identify_resource(resource))

        return os.path.getsize(url)

    response = None
    try:
        response = requests.head(url)
    except Exception, e:
        log.info("Unable to access resource {0}: {1}".format(url, e))
        raise ResourceError("Unable to access resource",
            "There was a problem retrieving the resource URL %s : %s" % \
                                    (identify_resource(resource), e))

    headers = {}
    for header, value in response.headers.iteritems():
        headers[header.lower()] = value

    # Redirect?
    # DR: requests handles redirects, so this section may be removed
    if response.status_code == 302 and redirects < REDIRECT_LIMIT:
        if "location" not in headers:
            raise ResourceError("Resource moved, but no Location provided by resource server",
                'Resource %s moved, but no Location provided by resource server: %s' % \
                                (url, identify_resource(resource)))

        # if our redirect location is relative, then we can only assume
        # it is relative to the url we've just requested.
        if not headers['location'].startswith('http'):
            loc = urlparse.urljoin(url, headers['location'])
        else:
            loc = headers['location']

        return get_resource_length(loc, resource, required=required,
            redirects=redirects + 1)

    if 'content-length' in headers:
        length = int(headers['content-length'])
        return length

    # DR: I don't see how content-disposition is related to content-length
    #     so I suggest we remove this section.
    if required:
        # Content length not always set with content-disposition so we will
        # just have to take a flyer on it.
        if not 'content-disposition' in headers:
            log.info('No content-length returned for server: %s'
                                    % (url))
            raise ResourceError("Unable to get content length",
                'Unable to find the size of the remote resource: %s' % \
                                    identify_resource(resource))
    return None


def error(**vars):
    return json.dumps(dict(error=vars), indent=4)

def sizeof_fmt(num, decimal_places=1):
    '''Given a number of bytes, returns it in human-readable format.
    >>> sizeof_fmt(168963795964)
    '157.4GB'
    '''
    try:
        num = float(num)
    except ValueError:
        return num
    format_string = '%%3.%sf%%s' % decimal_places
    for x in ['bytes','KB','MB','GB']:
        if num < 1024.0:
            return format_string % (num, x)
        num /= 1024.0
    return format_string % (num, 'TB')


def _open_file(url):
    return open(url, 'r')


def _open_url(url):
    """ URLs with &pound; in, just so, so wrong.

    Errors fetching the URL are ignored.
    """
    try:
        return urllib2.urlopen(url.encode("utf-8"))
    except Exception, e:
        log.info("URL %s caused: %s" % (url, e))

    return None


def proxy_query(resource, url, query):
    '''
    Given the URL for a data file, return its transformed contents in JSON form.

    e.g. if it is a spreadsheet, it returns a JSON dict:
        {
            "fields": ['Name', 'Age'],
            "data": [['Bob', 42], ['Jill', 54]],
            "max_results": 10,
            "length": 435,
            "url": "http://data.com/file.csv",
        }
    Whatever it is, it always has length (file size in bytes) and url (where
    it got the data from, which might be a URL or a local cache filepath).

    May raise RequestError.

    :param resource: resource object
    :param url: URL or local filepath
    :param query: dict about the URL:
          type - (optional) format of the file - extension or mimetype.
                            Only specify this if you the caller knows better
                            than magic can detect it.
                            Defaults to the file extension of the URL.
          length - (optional) size of the file. If not supplied,
                              it will determine it.
          size_limit - max size of the file to transform
          indent - (optional) the indent for the pprint the JSON result
    '''
    parts = urlparse.urlparse(url)

    # Get resource type - first try to see whether there is type= URL option,
    # if there is not, try to get it from file extension

    if parts.scheme not in ['http', 'https']:
        query['handler'] = _open_file
    else:
        query['handler'] = _open_url

    resource_type = query.get("type")
    if not resource_type:
        resource_type = os.path.splitext(parts.path)[1]

    if not resource_type:
        raise RequestError('Could not determine the resource type',
            'If file has no type extension, specify file type in type= option')

    resource_type = re.sub(r'^\.', '', resource_type.lower())
    try:
        trans = transformer(resource_type, resource, url, query)
        if not trans:
            raise Exception("No transformer for %s" % resource_type)
    except Exception, e:
        raise RequestError('Resource type not supported',
            'Transformation of resource of type %s is not supported.'
            % (resource_type))

    length = query.get('length',
                       get_resource_length(url, resource,
                                           trans.requires_size_limit))

    log.debug('The file at %s has length %s', url, length)

    max_length = int(query['size_limit'])

    if length and trans.requires_size_limit and int(length) > max_length:
        raise ResourceError('The requested file is too large to preview',
                            'Requested resource is %s. '
                            'Size limit is %s. Resource: %s'
                            % (sizeof_fmt(length),
                               sizeof_fmt(max_length, decimal_places=0),
                               identify_resource(resource)))

    try:
        result = trans.transform()
    except ResourceError, reserr:
        log.debug('Transformation of %s failed. %s', url, reserr)
        raise reserr
    except StopIteration as si:
        # In all likelihood, there was no data to read
        log.debug('Transformation of %s failed. %s', url, si)
        raise ResourceError("Data Transformation Error",
            "There was a problem reading the resource data: %s" % \
                                    identify_resource(resource))
    except Exception, e:
        log.exception(e)
        raise ResourceError("Data Transformation Error",
                            "Data transformation failed: %s %s" % \
                                    (identify_resource(resource), e))

    indent = None

    if url.startswith('http'):
        result["url"] = url
    else:
        result["url"] = resource.cache_url or resource.url

    result["length"] = length or 0

    if 'indent' in query:
        indent = int(query.getfirst('indent'))

    return json.dumps(result, indent=indent)

def identify_resource(resource):
    '''Returns a printable identity of a resource object.
    e.g. '/dataset/energy-data/d1bedaa1-a1a3-462d-9a25-7b39a941d9f9'
    '''
    dataset_name = resource.resource_group.package.name if resource.resource_group else '?'
    return '/dataset/{0}/resource/{1}'.format(dataset_name, resource.id)

def fix_url(url):
    """
    DR: Any Unicode characters in a URL become encoded in UTF8.
    It does this by unquoting, encoding, and quoting again.
    RJ: Fixes urls so that they don't break when we're given utf8
    urls
    """
    if not isinstance(url,unicode):
        url = url.decode('utf8')

    # parse it
    parsed = urlparse.urlsplit(url)

    # divide the netloc further
    userpass,at,hostport = parsed.netloc.rpartition('@')
    user,colon1,pass_ = userpass.partition(':')
    host,colon2,port = hostport.partition(':')

    # encode each component
    scheme = parsed.scheme.encode('utf8')
    user = urllib.quote(user.encode('utf8'))
    colon1 = colon1.encode('utf8')
    pass_ = urllib.quote(pass_.encode('utf8'))
    at = at.encode('utf8')
    host = host.encode('idna')
    colon2 = colon2.encode('utf8')
    port = port.encode('utf8')
    path = '/'.join(  # could be encoded slashes!
        urllib.quote(urllib.unquote(pce).encode('utf8'),'')
        for pce in parsed.path.split('/')
    )
    query = urllib.quote(urllib.unquote(parsed.query).encode('utf8'),'=&?/')
    fragment = urllib.quote(urllib.unquote(parsed.fragment).encode('utf8'))

    # put it back together
    netloc = ''.join((user,colon1,pass_,at,host,colon2,port))
    return urlparse.urlunsplit((scheme,netloc,path,query,fragment))
