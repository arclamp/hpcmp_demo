import csv
import types

from girder.api import access
from girder.api.rest import Resource, loadmodel, RestException
from girder.api.describe import Description, autoDescribeRoute, describeRoute
from girder.constants import AccessType, TokenScope


def add_linebuffering(h):
    h._nextbuf = b''

    def x__iter__(self):
        return self

    def xnext(self):
        while b'\n' not in self._nextbuf:
            chunk = self.read(100)
            if not len(chunk):
                if not len(self._nextbuf):
                    raise StopIteration
                data = self._nextbuf
                self._nextbuf = b''
                return data
            self._nextbuf += chunk
            if b'\n' in self._nextbuf:
                break
        data, self._nextbuf = self._nextbuf.split(b'\n', 1)
        return data

    def xreadline(self):
        return self.next()

    h.__iter__ = types.MethodType(x__iter__, h)
    h.next = types.MethodType(xnext, h)
    h.readline = types.MethodType(xreadline, h)

    return h


class HPCMP(Resource):
    def __init__(self):
        super(HPCMP, self).__init__();
        self.resourceName = 'hpcmp'

        self.route('GET', ('stream',), self.get_streams)
        self.route('POST', ('stream', ':id'), self.open_stream)
        self.route('POST', ('stream', ':id', 'read'), self.read_stream)
        self.route('DELETE', ('stream', ':id'), self.close_stream)

        self.table = {}
        self.headers = {}

    @access.public(TokenScope.DATA_READ)
    @autoDescribeRoute(
        Description('Return all existing streams')
        .errorResponse('Read access was denied on this journal.', 403)
    )
    def get_streams(self, params):
        return self.table.keys()

    @access.public(TokenScope.DATA_READ)
    @autoDescribeRoute(
        Description('Open a new stream for reading')
        .modelParam('id', model='item', level=AccessType.READ)
        .param('header', 'Does the csv file contain a header?', dataType='boolean', required=False)
        .errorResponse('Read access was denied on this journal.', 403)
    )
    def open_stream(self, item, params):
        id = item['_id']
        header = params.get('header')

        if id in self.table:
            return False

        it = self.model('item').load(id, level=AccessType.READ, user=self.getCurrentUser())
        file = self.model('item').childFiles(it).next()

        f = add_linebuffering(self.model('file').open(file))
        self.table[id] = f

        if header:
            self.headers[id] = csv.reader([f.readline()]).next()
            return self.headers[id]

        return id

    @access.public(TokenScope.DATA_READ)
    @autoDescribeRoute(
        Description('Read a line from a stream')
        .modelParam('id', model='item', level=AccessType.READ)
        .param('lines', 'How many lines to read', required=False)
        .errorResponse('Read access was denied on this journal.', 403)
    )
    def read_stream(self, item, params):
        id = item['_id']
        lines = int(params.get('lines') or 1)

        if id not in self.table:
            raise RestException('No such stream {}'.format(id))

        f = self.table[id]

        data = []
        more = True
        for i in range(lines):
            try:
                line = f.readline()
            except StopIteration:
                more = False
                del self.table[id]
                break

            data.append(line)

        data = list(csv.reader(data))

        if self.headers[id]:
            data = map(lambda x: dict(zip(self.headers[id], x)), data)

        return {
            'data': data,
            'more': more
        }

    @access.public(TokenScope.DATA_READ)
    @autoDescribeRoute(
        Description('Delete a stream')
        .modelParam('id', model='item', level=AccessType.READ)
        .errorResponse('Read access was denied on this journal.', 403)
    )
    def close_stream(self, item, params):
        id = item['_id']

        present = id in self.table

        if present:
            del self.table[item['_id']]

        return present


def load(info):
    info['apiRoot'].hpcmp = HPCMP()
