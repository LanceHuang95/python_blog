import logging;logging.basicConfig(level=logging.INFO)
import asyncio
from aiohttp import web

async def index(request):
    return web.Response(body=b'<h1>Awesome</h1>', headers={'content-type':'text/html'})

def init():
    app = web.Application()
    app.router.add_get('/', index)
    web.run_app (app, host='127.0.0.1', port=9000)
    # srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    logging.info('server started at https://127.0.0.1:9000 ...')
    # return srv

# loop = asyncio.get_event_loop()
# # tasks = [hello(), hello()]
# # loop.run_until_complete(asyncio.wait(tasks))
# loop.run_until_complete(init(loop))
# loop.run_forever()

if __name__ == '__main__':
    init()