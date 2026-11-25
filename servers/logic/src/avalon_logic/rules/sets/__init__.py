"""手工改写成效果数据的套装档位（M2 试写 + M3 各批次）。

迁移工具按效果名称对应到套装档位：多档套装写"套装名·N件"，只有一档的直接写套装名。
全部改写完、写入规则库之后，这些只作为第一个规则版本的初始内容；之后的修改都在规则库里进行。
"""

from __future__ import annotations

from ..samples import TRIAL_EFFECTS
from .batch1 import BATCH1
from .batch2 import BATCH2
from .batch3 import BATCH3
from .batch4 import BATCH4
from .batch5 import BATCH5
from .batch6 import BATCH6
from .batch7 import BATCH7
from .batch8 import BATCH8
from .batch9 import BATCH9

WRITTEN_EFFECTS = [*TRIAL_EFFECTS, *BATCH1, *BATCH2, *BATCH3, *BATCH4, *BATCH5, *BATCH6, *BATCH7, *BATCH8, *BATCH9]
