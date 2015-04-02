import asyncio
import json
import aiohttp_mako

from aiohttp import web
from aiohttp_sse import EventSourceResponse

from .tbtools.console import _ConsoleFrame
from .utils import TEMPLATE_KEY, APP_KEY, ROOT_ROUTE_NAME, STATIC_ROUTE_NAME




@aiohttp_mako.template('toolbar.dbtmako', app_key=TEMPLATE_KEY)
def request_view(request):
    settings = request.app[APP_KEY]['settings']
    history = request.app[APP_KEY]['request_history']

    try:
        last_request_pair = history.last(1)[0]
    except IndexError:
        last_request_id = None
    else:
        last_request_id = last_request_pair[0]

    request_id = request.match_info.get('request_id', last_request_id)

    toolbar = history.get(request_id, None)

    panels = toolbar.panels if toolbar else []
    global_panels = toolbar.global_panels if toolbar else []

    static_path = request.app.router[STATIC_ROUTE_NAME].url(filename='')
    root_path = request.app.router[ROOT_ROUTE_NAME].url()

    button_style = settings.get('button_style', '')
    max_visible_requests = settings['max_visible_requests']

    hist_toolbars = history.last(max_visible_requests)

    return {'panels': panels,
            'static_path': static_path,
            'root_path': root_path,
            'button_style': button_style,
            'history': hist_toolbars,
            'global_panels': global_panels,
            'request_id': request_id,
            'request': toolbar.request if toolbar else None
            }

@asyncio.coroutine
def sse(request):
    # looks like sse is redurant here
    # TODO: consider move to ajax
    response = EventSourceResponse()
    response.start(request)
    history = request.app[APP_KEY]['request_history']

    active_request_id = str(request.match_info.get('request_id'))
    client_last_request_id = str(request.headers.get('Last-Event-Id', 0))

    max_visible_requests = 10
    if history:
        last_request_pair = history.last(1)[0]
        last_request_id = last_request_pair[0]
        if not last_request_id == client_last_request_id:
            data = []
            for _id, toolbar in history.last(max_visible_requests):
                req_type = 'active' if active_request_id == _id else ''
                data.append([_id, toolbar.json, req_type])

            if data:
                _data = json.dumps(data)
                response.send(_data, event='new_request', id=last_request_id)
                response.stop_streaming()
    return response


class ExceptionDebugView:

    # TODO: validate request

    # def __init__(self, request):
    #     if exc_history is None:
    #         raise HTTPBadRequest('No exception history')
    #     if not token:
    #         raise HTTPBadRequest('No token in request')
    #     if not token == request.registry.parent_registry.pdtb_token:
    #         raise HTTPBadRequest('Bad token in request')


    def _exception_history(self, request):
        return request.app[APP_KEY]['exc_history']

    def _get_frame(self, request):
        frm = request.GET.get('frm')
        if frm is not None:
            frm = int(frm)
        return frm

    def _get_tb(self, request):
        tb = request.GET.get('tb') or request.POST.get('tb')
        if tb is not None:
            tb = int(tb)
        return tb

    def _get_cmd(self, request):
        cmd = request.GET.get('cmd') or request.POST.get('cmd')
        return cmd

    # route_name='debugtoolbar.exception',
    @asyncio.coroutine
    def exception(self, request):
        tb_id = self._get_tb(request)
        tb = self._exception_history(request).tracebacks[tb_id]
        body = tb.render_full(request).encode('utf-8', 'replace')
        import ipdb; ipdb.set_trace()
        response = web.Response(body, status=500)
        return response

    @aiohttp_mako.template('debugtoolbar.source',  app_key=TEMPLATE_KEY)
    def source(self, request):
        exc_history = self._exception_history(request)
        _frame = self._get_frame(request)
        if _frame is not None:
            frame = exc_history.frames.get(_frame)
            if frame is not None:
                body = frame.render_source()
                return web.Response(body=body, content_type='text/html')
        return web.HTTPBadRequest()

    def execute(self, request):

        _exc_history = self._exception_history(request)
        if _exc_history.eval_exc:
            exc_history = _exc_history
            cmd = self._get_cmd(request)
            frame = self._get_frame(request)
            if frame is not None and cmd is not None:
                frame = exc_history.frames.get(frame)
                if frame is not None:
                    result = frame.console.eval(cmd)
                    return web.Response(body=result, content_type='text/html')
        return web.HTTPBadRequest()

    @aiohttp_mako.template('console.dbtmako',  app_key=TEMPLATE_KEY)
    def console(self, request):
        static_path = request.app.router[STATIC_ROUTE_NAME].url(filename='')
        root_path = request.app.router[ROOT_ROUTE_NAME].url()
        token = request.GET.get('token')
        tb = self._get_tb(request)


        _exc_history = self._exception_history(request)
        vars = {
            'evalex':           _exc_history.eval_exc and 'true' or 'false',
            'console':          'true',
            'title':            'Console',
            'traceback_id':     tb or -1,
            'root_path':        root_path,
            'static_path':      static_path,
            'token':            token,
            }
        if 0 not in _exc_history.frames:
            _exc_history.frames[0] = _ConsoleFrame({})
        return vars
