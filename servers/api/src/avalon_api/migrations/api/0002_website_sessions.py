from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('api', '0001_initial')]

    initial = False

    operations = [
        ops.CreateModel(
            name='WebSession',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('user', fields.ForeignKeyField('api.AdminUser', source_field='user_id', db_constraint=True, to_field='id', related_name='sessions', on_delete=OnDelete.CASCADE)),
                ('token_hash', fields.CharField(unique=True, max_length=64)),
                ('credential_version', fields.CharField(max_length=64)),
                ('expires_at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=False)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'web_sessions', 'app': 'api', 'pk_attr': 'id', 'table_description': '网站会话：只存令牌哈希；账号由 SQL 手动入库，运行时不创建账号。'},
            bases=['Model'],
        ),
        ops.AddField(
            model_name='AdminUser',
            name='last_login_at',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
    ]
