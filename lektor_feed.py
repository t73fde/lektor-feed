# -*- coding: utf-8 -*-
import hashlib
import uuid
from datetime import datetime, date

import pkg_resources
from lektor.build_programs import BuildProgram
from lektor.db import F
from lektor.environment import Expression
from lektor.pluginsystem import Plugin
from lektor.context import get_ctx, url_to
from lektor.sourceobj import VirtualSourceObject
from lektor.utils import build_url

from werkzeug.contrib.atom import AtomFeed
from markupsafe import escape


class AtomFeedSource(VirtualSourceObject):
    def __init__(self, parent, feed_id, plugin):
        VirtualSourceObject.__init__(self, parent)
        self.plugin = plugin
        self.feed_id = feed_id

    @property
    def path(self):
        return self.parent.path + '@atom/' + self.feed_id

    @property
    def url_path(self):
        p = self.plugin.get_feed_config(self.feed_id, 'url_path')
        if p:
            return p

        return build_url([self.parent.url_path, self.filename])

    def __getattr__(self, item):
        try:
            return self.plugin.get_feed_config(self.feed_id, item)
        except KeyError:
            raise AttributeError(item)

    @property
    def feed_name(self):
        return self.plugin.get_feed_config(self.feed_id, 'name') or \
            self.feed_id


def get(item, field, default=None):
    if field in item:
        return item[field]
    return default


def get_id(s):
    return uuid.UUID(bytes=hashlib.md5(s).digest(), version=3).urn


def get_item_title(item, field):
    if field in item:
        return item[field]
    return item.record_label


def get_item_body(item, field):
    if field not in item:
        raise RuntimeError('Body field %r not found in %r' % (field, item))
    with get_ctx().changed_base_url(item.url_path):
        return unicode(escape(item[field]))


def get_item_updated(item, field):
    if field in item:
        rv = item[field]
    else:
        rv = datetime.utcnow()
    if isinstance(rv, date) and not isinstance(rv, datetime):
        rv = datetime(*rv.timetuple()[:3])
    return rv


class AtomFeedBuilderProgram(BuildProgram):
    def produce_artifacts(self):
        self.declare_artifact(
            self.source.url_path,
            sources=list(self.source.iter_source_filenames()))

    def build_artifact(self, artifact):
        ctx = get_ctx()
        feed_source = self.source
        blog = feed_source.parent

        summary = get(blog, feed_source.blog_summary_field) or ''
        subtitle_type = ('html' if hasattr(summary, '__html__') else 'text')
        blog_author = unicode(get(blog, feed_source.blog_author_field) or '')
        generator = ('Lektor Feed Plugin',
                     'https://yoyod.de/p/lektor-feed',
                     pkg_resources.get_distribution('lektor-feed').version)

        project_id = ctx.env.load_config().base_url
        if not project_id:
            project_id = ctx.env.project.id
        feed = AtomFeed(
            title=feed_source.feed_name,
            subtitle=unicode(summary),
            subtitle_type=subtitle_type,
            author=blog_author,
            feed_url=url_to(feed_source, external=True),
            url=url_to(blog, external=True),
            id=get_id(project_id),
            generator=generator)

        if feed_source.items:
            # "feed_source.items" is a string like "site.query('/blog')".
            expr = Expression(ctx.env, feed_source.items)
            items = expr.evaluate(ctx.pad)
        else:
            items = blog.children

        if feed_source.item_model:
            items = items.filter(F._model == feed_source.item_model)

        order_by = '-' + feed_source.item_date_field
        items = items.order_by(order_by).limit(int(feed_source.limit))

        for item in items:
            item_author_field = feed_source.item_author_field
            item_author = get(item, item_author_field) or blog_author

            feed.add(
                get_item_title(item, feed_source.item_title_field),
                get_item_body(item, feed_source.item_body_field),
                xml_base=url_to(item, external=True),
                url=url_to(item, external=True),
                content_type='html',
                id=get_id(u'%s/%s' % (
                    project_id,
                    item['_path'].encode('utf-8'))),
                author=item_author,
                updated=get_item_updated(item, feed_source.item_date_field))

        with artifact.open('wb') as f:
            f.write(feed.to_string().encode('utf-8'))


class FeedPlugin(Plugin):
    name = u'Lektor Feed plugin'

    defaults = {
        'source_path': '/',
        'name': None,
        'url_path': None,
        'filename': 'feed.xml',
        'blog_author_field': 'author',
        'blog_summary_field': 'summary',
        'items': None,
        'limit': 50,
        'item_title_field': 'title',
        'item_body_field': 'body',
        'item_author_field': 'author',
        'item_date_field': 'pub_date',
        'item_model': None,
    }

    def get_feed_config(self, feed_id, key):
        default_value = self.defaults[key]
        return self.get_config().get('%s.%s' % (feed_id, key), default_value)

    def on_setup_env(self, **extra):
        self.env.add_build_program(AtomFeedSource, AtomFeedBuilderProgram)

        @self.env.virtualpathresolver('atom')
        def feed_path_resolver(node, pieces):
            if len(pieces) != 1:
                return

            _id = pieces[0]

            config = self.get_config()
            if _id not in config.sections():
                return

            source_path = self.get_feed_config(_id, 'source_path')
            if node.path == source_path:
                return AtomFeedSource(node, _id, plugin=self)

        @self.env.generator
        def generate_feeds(source):
            for _id in self.get_config().sections():
                if source.path == self.get_feed_config(_id, 'source_path'):
                    yield AtomFeedSource(source, _id, self)
