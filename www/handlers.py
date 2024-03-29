from ast import keyword
from ntpath import join
from pydoc import pager
import re, time, json, logging, hashlib, base64, asyncio
from tkinter import N

## markdown 是处理日志文本的一种格式语法，具体语法使用请百度
import markdown
from aiohttp import web
from coroweb import get, post

## 分页管理以及调取API时的错误信息
from apis import Page, APIError, APIValueError, APIPermissionError, APIResourceNotFoundError
from models import User, Comment, Blog, next_id
from config import configs

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret


# 网站所需要的后端API, 前端页面URL的列表：

# 后端API包括：
# 如果一个URL返回的不是HTML，而是机器能直接解析的数据，这个URL就可以看成是一个Web API。
# REST就是一种设计API的模式。最常用的数据格式是JSON。由于JSON能直接被JavaScript读取，所以，以JSON格式编写的REST风格的API具有简单、易读、易用的特点。
# 编写API有什么好处呢？由于API就是把Web App的功能全部封装了，所以，通过API操作数据，可以极大地把前端和后端的代码隔离，使得后端代码易于测试，前端代码编写更简单。
# 一个API也是一个URL的处理函数，我们希望能直接通过一个@api来把函数变成JSON格式的REST API，这样，获取注册用户可以用一个API实现如下

# 获取日志：GET /api/blogs
# 创建日志：POST /api/blogs
# 搜索日志：POST /api/blogs/search/{name}
# 修改日志：POST /api/blogs/:blog_id
# 删除日志：POST /api/blogs/:blog_id/delete
# 获取评论：GET /api/comments
# 创建评论：POST /api/blogs/:blog_id/comments
# 删除评论：POST /api/comments/:comment_id/delete
# 创建新用户：POST /api/users
# 获取用户：GET /api/users
# 删除用户: POST /api/users/{id}/delete
# 修改用户： 未实现
# 管理页面包括：

# 评论列表页：GET /manage/comments
# 日志列表页：GET /manage/blogs
# 创建日志页：GET /manage/blogs/create
# 修改日志页：GET /manage/blogs/
# 用户列表页：GET /manage/users
# 用户浏览页面包括：

# 注册页：GET /register
# 登录页：GET /signin
# 注销页：GET /signout
# 首页：GET /
# 站内搜索：GET /search/{name}
# 日志详情页：GET /blog/:blog_id

## 查看是否是管理员用户
def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()

## 获取页码信息
def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p

## 计算加密cookie，注册和登录时生成cookie
def user2cookie(user, max_age):
    # build cookie string by: id-expires-sha1
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' %(user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

## 文本转HTML
def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)

## 解密cookie，app.py中auth_factory函数校验cookie
async def cookie2user(cookie_str):
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time():
            return None
        user = await User.find(uid)
        if user is None:
            return None
        s = '%s-%s-%s-%s' %(uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None

# TODO 用户浏览页面
## 处理首页URL
@get('/')
async def index(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return {
        '__template__': 'blogs.html',
        'page': p,
        'blogs': blogs
    }

## 处理日志详情页面URL
@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
    # markdown 代码块和高亮显示、自动生成目录
    for c in comments:
        c.html_content = markdown.markdown(c.content, extensions=['markdown.extensions.extra', 'markdown.extensions.codehilite', 'markdown.extensions.toc'])
    blog.html_content = markdown.markdown(blog.content, extensions=['markdown.extensions.extra', 'markdown.extensions.codehilite', 'markdown.extensions.toc'])
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }

## 站内搜索 按标题搜索日志页面，目前只支持精确匹配
@get('/search/{name}')
# 解析如下字符串： '?name=期末总结&btnG='
async def search_blog(name=None):
    logging.info('search name = %s' %name)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    # 用户使用搜索框 搜索
    if re.findall(r'&btnG=', name):
        name = (name.split('='))[1].split('&')[0]
    else:
    # 用户使用地址直接搜索
        name = (name.split('='))[0].split('&')[0]
    blogs = await Blog.findAll('name=?',[name])
    p = Page(len(blogs), 1)
    return {
        '__template__': 'search.html',
        'page': p,
        'blogs': blogs
    }

 ## 处理注册页面URL
@get('/register')
def register():
    return {
       '__template__': 'register.html'
    }

## 处理登录页面URL
@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }

## 用户登录验证API
@post('/api/authenticate')
async def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    # 此处传入的passwd已经是sign.html中加密过的
    # passwd: this.passwd==='' ? '' : CryptoJS.SHA1(email + ':' + this.passwd).toString()
    if not passwd:
        raise APIValueError('passwd', 'Invalid password.')
    users = await User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    # check passwd:SHA1是一种单向算法
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    # 此处判断数据库中保存的用户密码 和 sign.html 传入的email、passwd经过sha1是否相等
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid password.')
    # authenticate ok, set cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

## 用户注销
@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r

# TODO 管理页面
## 获取管理页面
@get('/manage/')
def manage():
    return 'redirect:/manage/comments'

## 评论管理页面
@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }

## 日志管理页面
@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }

## 创建日志页面
@get('/manage/blogs/create')
def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }

## 编辑日志页面
@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/%s' % id
    }

## 用户管理页面
@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }

# TODO 后端API:返回一个dict，后续的response这个middleware就可以把结果序列化为JSON并返回
## 获取评论信息API
@get('/api/comments')
async def api_comments(*, page='1'):
    page_index = get_page_index(page)
    num = await Comment.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)

## 用户发表评论API
@post('/api/blogs/{id}/comments')
async def api_create_comment(id, request, *, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('Please signin first.')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
    await comment.save()
    return comment

## 管理员删除评论API
@post('/api/comments/{id}/delete')
async def api_delete_comments(id, request):
    check_admin(request)
    c = await Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    await c.remove()
    return dict(id=id)

## 获取用户信息API
@get('/api/users')
async def api_get_users(*, page='1'):
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    for u in users:
        u.passwd = '******'
    return dict(page=p, users=users)

## 定义EMAIL和HASH的格式规范
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

## 用户注册API
@post('/api/users')
async def api_register_user(*, email, name, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    # 此处传入的passwd已经是register.html中加密过的
    # passwd: CryptoJS.SHA1(email + ':' + this.password1).toString()
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    uid = next_id()
    # 数据库中保存的passwd
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    # make session cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

## 获取日志列表API
@get('/api/blogs')
async def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)

## 获取日志详情API
@get('/api/blogs/{id}')
async def api_get_blog(*, id):
    blog = await Blog.find(id)
    return blog

# 搜索日志：
@get('/api/blogs/search/{name}')
async def api_search_blogs(*, name=None):
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    blogs = await Blog.findAll('name=?',[name])
    return dict(blogs=blogs)

## 发表日志API
@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary=summary.strip(), content=content.strip())
    await blog.save()
    return blog

## 编辑日志API
@post('/api/blogs/{id}')
async def api_update_blog(id, request, *, name, summary, content):
    check_admin(request)
    blog = await Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    await blog.update()
    return blog

## 删除日志API
@post('/api/blogs/{id}/delete')
async def api_delete_blog(request, *, id):
    check_admin(request)
    blog = await Blog.find(id)
    await blog.remove()
    return dict(id=id)

## 删除用户API
@post('/api/users/{id}/delete')
async def api_delete_users(id, request):
    check_admin(request)
    id_buff = id
    user = await User.find(id)
    if user is None:
        raise APIResourceNotFoundError('Comment')
    await user.remove()
    # 给被删除的用户在评论中标记
    comments = await Comment.findAll('user_id=?',[id])
    if comments:
        for comment in comments:
            id = comment.id
            c = await Comment.find(id)
            c.user_name = c.user_name + ' (该用户已被删除)'
            await c.update()
    id = id_buff
    return dict(id=id)