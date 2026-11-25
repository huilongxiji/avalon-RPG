from tortoise import migrations
from tortoise.migrations import operations as ops
import functools
from json import dumps, loads
from tortoise import fields

class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name='AdminUser',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('username', fields.CharField(unique=True, max_length=64)),
                ('password_hash', fields.CharField(max_length=256)),
                ('role', fields.CharField(default='editor', max_length=16)),
                ('disabled', fields.BooleanField(default=False)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'admin_users', 'app': 'api', 'pk_attr': 'id'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='AuditLog',
            fields=[
                ('id', fields.BigIntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=True)),
                ('actor', fields.CharField(max_length=64)),
                ('action', fields.CharField(max_length=64)),
                ('target', fields.CharField(default='', max_length=256)),
                ('detail', fields.JSONField(default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                ('ip', fields.CharField(default='', max_length=64)),
            ],
            options={'table': 'audit_log', 'app': 'api', 'pk_attr': 'id', 'table_description': '管理操作审计：只追加，不修改。'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='FeedToken',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('owner', fields.CharField(max_length=64)),
                ('token_hash', fields.CharField(unique=True, max_length=64)),
                ('note', fields.CharField(default='', max_length=128)),
                ('revoked', fields.BooleanField(default=False)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'feed_tokens', 'app': 'api', 'pk_attr': 'id', 'table_description': '数据源令牌：本地 Excel 读取实时数据用，只读，可以随时作废。'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='PlayerToken',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('openid', fields.CharField(db_index=True, max_length=64)),
                ('token_hash', fields.CharField(unique=True, max_length=64)),
                ('expires_at', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'player_tokens', 'app': 'api', 'pk_attr': 'id', 'table_description': '预留：以后安卓软件的玩家登录令牌（本期不实现）。'},
            bases=['Model'],
        ),
        ops.CreateModel(
            name='ServiceToken',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('name', fields.CharField(unique=True, max_length=64)),
                ('token_hash', fields.CharField(unique=True, max_length=64)),
                ('scopes', fields.JSONField(default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                ('revoked', fields.BooleanField(default=False)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'service_tokens', 'app': 'api', 'pk_attr': 'id', 'table_description': '服务令牌：bot 前端、模拟器调用 API 时使用。'},
            bases=['Model'],
        ),
    ]
