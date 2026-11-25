"""真实游戏请求中的资源变动随存档同事务记账；模拟与导入没有统计上下文。"""

from __future__ import annotations


class EconomyTracked:
    async def save(self, *args, **kwargs):
        from ..game import ledger

        context = ledger.current()
        if context is None:
            return await super().save(*args, **kwargs)
        fields = {'Wallet': ('coins', 'world_coins', 'bank'),
                  'Player': ('stamina', 'special_stamina', 'exp', 'level'), 'Pity': ('value',)}[type(self).__name__]
        before = await type(self).filter(**{self._meta.pk_attr: self.pk}).using_db(kwargs.get('using_db')).values(*fields) if self.pk else []
        await super().save(*args, **kwargs)
        old = before[0] if before else {key: 1 if key == 'level' else 0 for key in fields}
        owner = self.openid if type(self).__name__ == 'Player' else self.player_id
        for key in fields:
            if key == 'level':
                continue
            updated = kwargs.get('update_fields')
            if updated is not None and key not in updated and not (key == 'exp' and 'level' in updated):
                continue
            previous, balance = int(old[key]), int(getattr(self, key))
            detail = {}
            if key == 'exp':
                from ..game.economy import exp_to_next_for

                # 经验用累计经验记账，升级清空当前级经验不会被误算为消耗。
                previous += sum(exp_to_next_for(lv) for lv in range(1, int(old['level'])))
                balance += sum(exp_to_next_for(lv) for lv in range(1, self.level))
                detail = {'level': self.level, 'level_exp': self.exp}
            delta = balance - previous
            if delta:
                await ledger.emit('economy', owner, currency='pity' if key == 'value' else key,
                                  delta=delta, balance=balance, detail=detail)
