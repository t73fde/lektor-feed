from setuptools import setup

setup(
    name='lektor-feed',
    version='20180508.0',
    author=u'Detlef Stern',
    author_email='mail-python.org@yodod.de',
    license='MIT',
    py_modules=['lektor_feed'],
    install_requires=['MarkupSafe', 'Lektor'],
    tests_require=['lxml', 'pytest'],
    url='https://github.com/t73fde/lektor-feed',
    entry_points={
        'lektor.plugins': [
            'feed = lektor_feed:FeedPlugin',
        ]
    }
)
