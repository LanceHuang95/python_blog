import asyncio, logging, aiomysql
import time, uuid
logging.basicConfig(level=logging.INFO)

def log(sql, args=()):
    logging.info('SQL:%s' % sql)

# 创建连接池, 和同步方式(pymysql)不一样的是使用异步不能直接创建数据库连接conn，
# 需要先创建一个数据库连接池对象__pool通过这个数据库连接池对象来创建数据库连接。参考如下：
# https://www.cnblogs.com/minseo/p/15597428.html 
# https://www.cnblogs.com/minseo/p/15598555.html
async def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    # 连接池为全局变量，其他函数也可以调用
    global __pool
    __pool = await aiomysql.create_pool(
        # host = kw['host'] if 'host' in kw else 'localhost'
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )

# args 替换sql语句的格式化字符串，即mysql语句可以使用%s代表一个字符串，然后在args中使用对应的变量或参数替换，
# args为一个list或元组，即是一个有序的序列需要和mysql中的%s一一对应
# 例如sql='select * from table_name where id=?'  args=['12345']
# 相当于使用args中的参数替换sql中的? 结果如下：select * from table_name where id='12345'
async def select(sql, args, size=None):
    log(sql, args)
    global __pool
    with (await __pool) as conn:
        # 数据库连接对象conn加方法cursor创建一个数据库连接浮标
        cur = await conn.cursor(aiomysql.DictCursor)
        # SQL语句的占位符是?，而MySQL的占位符是%s，select()函数在内部自动替换。
        # 注意要始终坚持使用带参数的SQL，而不是自己拼接SQL字符串
        await cur.execute(sql.replace('?', '%s'), args or ())
        if size:
            # 获取查询的前几条结果，返回一个list，list元素是dict，dict元素是查询对应的键值对
            # eg:[{'id': '111111', 'email': 'test@qq.com'}]
            # 此外还有cursor.fetchone()，返回dict，游标移动到下一条数据，再执行一次又返回一条数据
            rs = await cur.fetchmany(size)
        else:
            rs = await cur.fetchall()
        await cur.close()
        # await conn.commit()   提交修改结果，否则修改不生效

        # 打印日志返回了几条数据
        logging.info('rows returned: %s' % len(rs))
        return rs

# insert update delete
async def execute(sql, args):
    log(sql)
    with (await __pool) as conn:
        try:
            cur = await conn.cursor()
            await cur.execute(sql.replace('?', '%s'), args)
            affected = cur.rowcount
            await cur.close()
        except BaseException as e:
            raise
        # 执行操作也是有返回的，返回结果是本次操作影响的数据库条数，
        # 如果把返回结果打印，本次输出为1，返回为0则代表没有影响数据库，代表修改失败
        return affected


# TODO 1. 测试create_pool
# 在mysql中创建数据库：create awesome_python3_webapp;

# loop = asyncio.get_event_loop()
# # 定义连接池的参数
# # 输出全局变量__pool为一个连接池对象
# kw = {'user':'www-data','password':'www-data','db':'awesome_webapp'}
# loop.run_until_complete(create_pool(loop=loop,**kw))
# print(__pool)

# 在awesome_webapp 数据库中过创建表users
# use awesome_python3_webapp; show tables; desc users;
# CREATE TABLE `users` (
#   `id` varchar(50) NOT NULL,
#   `email` varchar(50) NOT NULL,
#   `passwd` varchar(50) NOT NULL,
#   `admin` tinyint(1) NOT NULL,
#   `name` varchar(50) NOT NULL,
#   `image` varchar(500) NOT NULL,
#   `created_at` double NOT NULL,
#   PRIMARY KEY (`id`),
#   UNIQUE KEY `idx_email` (`email`),
#   KEY `idx_created_at` (`created_at`)
# );

# # TODO 2. 测试 execute 函数
# res = loop.run_until_complete(execute('insert into users values(123,"test1@qq.com","123456789",0,"liuym","http://image",1111111111)',[]))
# print(res)
# res = loop.run_until_complete(execute('update users set name="liuyueming" where email=?',["test1@qq.com"]))
# print(res)
# res=loop.run_until_complete(select('select * from users',[]))
# print(res)
# res = loop.run_until_complete(execute('delete from users where email=?',["test1@qq.com"]))
# print(res)



# 在编写ORM时，给一个Field增加一个default参数可以让ORM自己填入缺省值，非常方便。
# 并且，缺省值可以作为函数对象传入，在调用save()时自动计算
class Field(object):
    def __init__(self, name, column_type, primary_key, default) -> None:
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s, %s:%s>' %(self.__class__.__name__, self.column_type, self.name)

class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)') -> None:
        super().__init__(name, ddl, primary_key, default)

class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)

# 根据传递的整数生成一个字符串?,?,?...用于占位符
def create_args_string(num):
    L = []
    for i in range(num):
        L.append('?')
    return ', '.join(L)


class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        # 获取table名称:
        # 从字典attrs中获取属性__table__,如果在类中没有定义这个属性则返回None
        # 如果在属性中没有定义但是我们可以从参数name中获取到就是类名
        # 例如我们对类User进行重新创建,在类User中已经定义了属性 __table__ = 'users'
        # 所以我们优先得到的表名就是'users',假如没有定义则就是类名'User'
        tableName = attrs.get('__table__', None) or name
        logging.info('found model:%s (table:%s)' %(name, tableName))
        # logging.info("修改前attrs:%s" % attrs)
        # 获取所有的Field和主键名:
        # 定义一个空字典用于存储需要定义的类中除了默认属性以为定义的属性
        # 例如本次我们针对类User则使用mappings字典存储'id','email','passwd','admin','name','image','create_at'的属性
        # 它们对应的属性值是一个实例化以后的实例，例如id对应的属性值是通过类StringField实例化后的实例
        mappings = dict()
        fields = []
        # primaryKey用于存储主键字段名
        # 例如针对类User的主键名为'id'
        primaryKey = None
        # 如果找到一个Field属性，就把它保存到一个__mappings__的dict中，
        # 同时从类属性中删除该Field属性，否则，容易造成运行时错误（实例的属性会遮盖类的同名属性）
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
                # 然后通过实例的属性primary_key去找主键，如果找到了主键则赋值给primaryKey
                # 如果不是主键的字段则追加至fields这个list
                # 一个表只能有一个主键，如果有多个主键则抛出RuntimeError错误，错误提示为重复的主键
                if v.primary_key:
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found.')
        # 例如类User需要从原attrs中删除key值为 'id','email','passwd','admin','name','image','create_at'的元素
        for k in mappings.keys():
            attrs.pop(k)
        
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey # 主键属性名
        attrs['__fields__'] = fields # 除主键外的属性名
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句:
        # '__select__': 'select `id`, `email`, `passwd`, `admin`, `name`, `image`, `created_at` from `users`'
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        # '__insert__': 'insert into `users` (`email`, `passwd`, `admin`, `name`, `image`, `created_at`, `id`) values (?, ?, ?, ?, ?, ?, ?)'
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        # '__update__': 'update `users` set `email`=?, `passwd`=?, `admin`=?, `name`=?, `image`=?, `created_at`=? where `id`=?'
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        # '__delete__': 'delete from `users` where `id`=?'
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        # logging.info("修改后attrs:%s" % attrs)
        return type.__new__(cls, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)
    
    # __getattribute__ 获取属性时，一定会被调用，不论属性存不存在
    # __getattr__ 获取不存在的属性时会调用该方法
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key: str, value: str) -> None:
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        # getattr(),python内置函数，获取对象的属性和方法
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value
    
    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        ## find objects by where clause
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args:
            args = []
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        ## find number by select and where
        sql = ['select %s _num_ from `%s`' %(selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']
    
    @classmethod
    async def find(cls, pk):
        ## find object by primary key
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        # 不能返回rs[0]，rs[0]是字典，字典不是实例自然也就没有对应的类方法update和remove了
        return cls(**rs[0])

    async def save(self):
        # args获取用户传入的数据
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)
    
    async def update(self):
        # 注意此处使用self.getValue 获取属性，因为此处self一般为find 方法找到的Model对象，里面就是一个dict
        # self类似 这个字典{'id': '001', 'email': 'test2@qq.com', 'passwd': '1234567890', 'admin': 0, 'name': 'Test', 'image': 'about:blank', 'created_at': 1653139097.551685}
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)

    # @classmethod
    # def findAll(cls, where=None, args=None, **kw):
    #     ## find objects by where clause
    #     sql = [cls.__select__]
    #     if where:
    #         sql.append('where')
    #         sql.append(where)
    #     if args == None:
    #         args = []
    #     orderBy = kw.get('orderBy', None)
    #     if orderBy:
    #         sql.append('order by')
    #         sql.append(orderBy)
    #     limit = kw.get('limit', None)
    #     if limit is not None:
    #         sql.append('limit')
    #         if isinstance(limit, int):
    #             sql.append('?')
    #             args.append(limit)
    #         elif isinstance(limit, tuple) and len(limit) == 2:
    #             sql.append('?, ?')
    #             args.extend(limit)
    #         else:
    #             raise ValueError('Invalid limit value: %s' % str(limit))
    #     rs = select(' '.join(sql), args)
    #     return [cls(**r) for r in rs]

    # @classmethod
    # def findNumber(cls, selectField, where=None, args=None):
    #     ## find number by select and where
    #     sql = ['select %s _num_ from `%s`' %(selectField, cls.__table__)]
    #     if where:
    #         sql.append('where')
    #         sql.append(where)
    #     rs = select(' '.join(sql), args, 1)
    #     if len(rs) == 0:
    #         return None
    #     return rs[0]['_num_']
    
    # @classmethod
    # def find(cls, pk):
    #     ## find object by primary key
    #     rs = select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
    #     if len(rs) == 0:
    #         return None
    #     # 不能返回rs[0]，rs[0]是字典，字典不是实例自然也就没有对应的类方法update和remove了
    #     return cls(**rs[0])

    # def save(self):
    #     # args获取用户传入的数据
    #     args = list(map(self.getValueOrDefault, self.__fields__))
    #     args.append(self.getValueOrDefault(self.__primary_key__))
    #     rows = execute(self.__insert__, args)
    #     if rows != 1:
    #         logging.warning('failed to insert record: affected rows: %s' % rows)
    
    # def update(self):
    #     args = list(map(self.getValue, self.__fields__))
    #     args.append(self.getValue(self.__primary_key__))
    #     rows = execute(self.__update__, args)
    #     if rows != 1:
    #         logging.warning('failed to update by primary key: affected rows: %s' % rows)

    # def remove(self):
    #     args = [self.getValue(self.__primary_key__)]
    #     rows = execute(self.__delete__, args)
    #     if rows != 1:
    #         logging.warning('failed to remove by primary key: affected rows: %s' % rows)


if __name__ == '__main__':
    def next_id():
        return '%015d%s000' % (int(time.time() * 1000), uuid.uuid4().hex)
 
    # 定义用户User类
    class User(Model):
        # 自定义表名，如果不自定义可以使用类名作为表名
        # 在使用metaclass重新定义类时，通过方法__new__内部的参数name可以获取到类名
        __table__ = 'users'
        # 定义字段名,id作为主键
        id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
        email = StringField(ddl='varchar(50)')
        passwd = StringField(ddl='varchar(50)')
        admin = BooleanField()
        name = StringField(ddl='varchar(50)')
        image = StringField(ddl='varchar(500)')
        created_at = FloatField(default=time.time)

    # TODO 3.使用同步连接测试 Model类的save find update remove 方法
    import pymysql
    def create_pool(**kw):
        host=kw.get('host', 'localhost')
        port=kw.get('port', 3306)
        user=kw['user']
        password=kw['password']
        db=kw['db']
        # 创建全部变量，用于存储创建的连接池
        global conn
        conn = pymysql.connect(host=host, user=user, password=password, database=db,port=port)
        
    kw = {'user':'www-data','password':'www-data','db':'awesome_webapp'}
    # 把字典传入创建连接池函数，执行即创建了全局连接池conn，可以在查询，执行等函数调用执行
    create_pool(**kw)
    
    def select(sql,args,size=None):
        log(sql,args)
        cursor =  conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(sql.replace('?','%s'),args or ())
        if size:
            rs = cursor.fetchmany(size)
        else:
            rs = cursor.fetchall()
        cursor.close
        logging.info('rows returned: %s' % len(rs))
        return rs
    
    def execute(sql,args):
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(sql.replace('?','%s'),args)
            rs = cursor.rowcount
            cursor.close()
            conn.commit()
        except:
            raise
        return rs

    u = User(id='001', name='Test', email='test@qq.com', passwd='1234567890', image='about:blank')
    u.save()
    rs = User.find('001')
    print(rs)
    rs.email = 'test1@qq.com'
    rs.update()

    u2 = User(id='002', name='Test2', email='test2@qq.com', passwd='0123456789', image='about:blank')
    u2.save()

    rs2 = User.findAll(orderBy='id',limit=2)
    print(rs2)

    rs3 = User.findNumber(selectField='id')
    print(rs3)

    for r in rs2:
        r.remove()