# Copyright (c) xxx Authors. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import copy

from ppsci.arch.mlp import MLP  # isort:skip
from ppsci.arch.embedding_koopman import LorenzEmbedding  # isort:skip
from ppsci.arch.physx_transformer import PhysformerGPT2  # isort:skip
from ppsci.utils import logger  # isort:skip


__all__ = ["MLP", "LorenzEmbedding", "PhysformerGPT2", "build_model"]


def build_model(cfg):
    """Build model

    Args:
        cfg (AttrDict): Arch config.

    Returns:
        nn.Layer: Model.
    """
    cfg = copy.deepcopy(cfg)
    arch_cls = cfg.pop("name")
    arch = eval(arch_cls)(**cfg)

    logger.debug(str(arch))

    return arch
