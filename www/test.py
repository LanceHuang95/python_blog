import orm
import asyncio
from models import User, Blog, Comment

kw = {'user':'www-data','password':'www-data','db':'awesome_webapp'}

async def test(loop):
    await orm.create_pool(loop = loop,**kw)
    u = User(name='Test', email='test@qq.com', passwd='1234567890', image='about:blank')
    await u.save()
    orm.__pool.close()
    await orm.__pool.wait_closed()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test(loop))
    loop.close()