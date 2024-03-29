import logging; logging.basicConfig(level=logging.INFO)
import asyncio, os, json, time
from datetime import datetime
from aiohttp import request, web
from jinja2 import Environment, FileSystemLoader

## config 配置代码在后面会创建添加, 
from config import configs

import orm
from coroweb import add_routes, add_static

## handlers 是url处理模块, 当handlers.py在API章节里完全编辑完再将下一行代码的双井号去掉
from handlers import cookie2user, COOKIE_NAME

## 初始化jinja2的函数
def init_jinja2(app, **kw):
    logging.info('init jinja2...')
    options = dict(
        autoescape = kw.get('autoescape', True),
        block_start_string = kw.get('block_start_string', '{%'),
        block_end_string = kw.get('block_end_string', '%}'),
        variable_start_string = kw.get('variable_start_string', '{{'),
        variable_end_string = kw.get('variable_end_string', '}}'),
        auto_reload = kw.get('auto_reload', True)
        )
    path = kw.get('path', None)
    # 获得了当前执行的py文件的文件夹下的文件夹templates完整路径
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    logging.info('set jinja2 template path: %s' % path)
    # Environment: The core component of Jinja is the Environment. 
    # It contains important shared variables like configuration, filters, tests, globals and others.
    # FileSystemLoader: Load templates from a directory in the file system.
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get('filters', None)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    # 把修改后的env赋值给app的属性'__templating__'
    app['__templating__'] = env

## 以下是middleware,可以把通用的功能从每个URL处理函数中拿出来集中放到一个地方
## URL处理日志工厂
async def logger_factory(app, handler):
    async def logger(request):
        # logging.info('fn is "logger_factory",request=%s,handler=%s' % (request, handler))
        logging.info('Request: %s %s' % (request.method, request.path))
        return (await handler(request))
    return logger

# 利用middle在处理URL之前，把cookie解析出来，并将登录用户绑定到request对象上，这样，后续的URL处理函数就可以直接拿到登录用户：
# 认证处理工厂--把当前用户绑定到request上，并对URL/manage/进行拦截，检查当前用户是否是管理员身份
# 需要handlers.py的支持
async def auth_factory(app, handler):
   async def auth(request):
       logging.info('check user: %s %s' % (request.method, request.path))
       request.__user__ = None
       cookie_str = request.cookies.get(COOKIE_NAME)
       if cookie_str:
           user = await cookie2user(cookie_str)
           if user:
               logging.info('set current user: %s' % user.email)
               request.__user__ = user
       if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
           return web.HTTPFound('/signin')
       return (await handler(request))
   return auth

## 数据处理工厂
async def data_factory(app, handler):
    async def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = await request.json()
                logging.info('request json: %s' % str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = await request.post()
                logging.info('request form: %s' % str(request.__data__))
        return (await handler(request))
    return parse_data

## 响应返回处理工厂
async def response_factory(app, handler):
    async def response(request):
        logging.info('fn is "response_factory",request=%s,handler=%s' % (request, handler))
        # handler(request) 会跳转到coroweb.py中async def __call__(self, request)
        r = await handler(request)
        # r:{'__template__': 'test.html', 'users': [{'id': '111', 'email': 'test@qq.com', 'passwd': '1234567890', 'admin': 0, 'name': 'Test', 'image': 'about:blank', 'created_at': 1637895583.49905}]}
        # (app['__templating__'].get_template(template)): <Template 'test.html'>
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')
            if template is None:
                resp = web.Response(body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                ## 在handlers.py完全完成后,去掉下一行的双井号
                r['__user__'] = request.__user__
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        if isinstance(r, int) and r >= 100 and r < 600:
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and t >= 100 and t < 600:
                return web.Response(t, str(m))
        # default:
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp
    return response


# 时间转换函数，传递一个时间戳计算与当前时间的相差时间
def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta // 3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)

async def init(loop):
    await orm.create_pool(loop = loop,**configs.db)
    # 通过web生成一个app
    ## 在handlers.py完全完成后,在下面middlewares的list中加入auth_factory
    # URL在被某个函数处理钱，会经过middlewares拦截器处理
    app = web.Application(middlewares=[
        logger_factory, response_factory, auth_factory
    ])
    # datetime filter（过滤器），把一个浮点数转换成日期字符串，在blogs中使用
    init_jinja2(app, filters=dict(datetime=datetime_filter))
    add_routes(app, 'handlers')
    add_static(app)
    runner = web.AppRunner(app)
    await runner.setup()
    srv = web.TCPSite(runner, 'localhost', 9000)
    logging.info('server started at https://127.0.0.1:9000 ...')
    await srv.start()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init(loop))
    loop.run_forever()