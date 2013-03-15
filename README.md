# ckanext-datapreview

This extension is a modified, but local implementation of the [OKFN dataproxy](https://github.com/okfn/dataproxy) that runs as a CKAN extension rather than on [Google AppEngine](http://jsonpdataproxy.appspot.com). This has been written to improve the performance on [data.gov.uk](data.gov.uk) and increase the maximum file size processed.

The interface to the extension::

    /data/preview/<resource_id>?max-results=N&encoding=utf-8

is not exactly the same - dataproxy requires the URL instead of the resource id - the data returned is identical. Rather than always fetching the data from the remote site the new controller at the above route will first attempt to find the data in the [ckanext-archiver](https://github.com/okfn/ckanext-archiver)'s local archive.

## Installation

The most straightforward method of installation is::

    git clone git://github.com/rossjones/ckanext-datapreview.git
    cd ckanext-datapreview
    python setup.py develop

Once complete the datapreview should be added to your ckan.plugins property in the appropriate .ini file.


## Requirements

* __XLRD__ - retrieved by setup.py
* __ckanext-archiver__ - for the resource cache

As this extension is based on the dataproxy it is currently using the same old copy of brewery (0.5.0) which is not available in pypi (link for 0.5.0 version references tip in a HG repo). It is included in this source code repository.

## Problems

Currently when previewing this data with [recline.js](reclinejs.com) the dataproxy backend has a hard-coded URL to http://jsonpdataproxy.appspot.com which means it is unable to be used with this extension.

On data.gov.uk we have patched a local copy of recline to use the new datapreview, however a patch to the recline dataproxy backend should be feasible.

## Improvements

* Increases the limit on download size (doesn't have the appengine download limit)
* Uses the local archive cache if it exists rather than hitting the remote site (only if ckanext-archiver has retrieved the file).







