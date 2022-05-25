# 默认的配置文件

configs = {
    'debug': True,
    'db': {
        'host': '127.0.0.1',
        # 'host': 'localhost',
        'port': 3306,
        'user': 'www-data',
        'password': 'www-data',
        'db': 'awesome_webapp'
    },
    'session': {
        'secret': 'Awesome'
    }
}