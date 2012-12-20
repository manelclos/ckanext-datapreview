"""Data Proxy - CSV transformation adapter"""
import urllib2
import csv
from ckanext.datapreview.transform.base import Transformer
import brewery.ds as ds

try:
    import json
except ImportError:
    import simplejson as json

class CSVTransformer(Transformer):
    def __init__(self, resource, url, query):
        super(CSVTransformer, self).__init__(resource, url, query)
        self.requires_size_limit = False

        if 'encoding' in self.query:
            self.encoding = self.query["encoding"]
        else:
            self.encoding = 'utf-8'

        if 'dialect' in self.query:
            self.dialect = self.query["dialect"]
        else:
            self.dialect = None

    def _might_be_html(self, content):
        count = content.count('<')

        if count >= 3:
            if content.count('>') > 1:
                return dict(title="Invalid content",
                    message="This content appears to be HTML and not tabular data")
        return None


    def transform(self):
        handle = self.open_data(self.url)

        if not self.dialect:
            if self.url.endswith('.tsv'):
                self.dialect = 'excel-tab'
            else:
                self.dialect = 'excel'

        src = ds.CSVDataSource(handle, encoding=self.encoding, dialect=self.dialect)
        src.initialize()

        try:
            result = self.read_source_rows(src)
        except:
            # We so often get HTML when someone tells us it is CSV
            # that we will have this extra special check JUST for this
            # use-case.
            if hasattr(handle, 'close'):
                handle.close()

            check = self._might_be_html(self.open_data(self.url).read())
            if check:
                return check
            raise


        if hasattr(handle, 'close'):
            handle.close()

        return result

