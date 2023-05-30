# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The initialization method under this module is aligned with pytorch initialization.
If you need to use the initialization method of PaddlePaddle, please refer to
[paddle.nn.initializer](https://github.com/PaddlePaddle/Paddle/tree/develop/python/paddle/nn/initializer)

This code is based on [torch.nn.init](https://github.com/pytorch/pytorch/blob/main/torch/nn/init.py)
Ths copyright of pytorch/pytorch is a BSD-style license, as found in the LICENSE file.
"""

import math

import numpy as np
import paddle
from paddle import nn
from typing_extensions import Literal

from ppsci.utils import logger

__all__ = [
    "uniform_",
    "normal_",
    "trunc_normal_",
    "constant_",
    "ones_",
    "zeros_",
    "xavier_uniform_",
    "xavier_normal_",
    "kaiming_uniform_",
    "kaiming_normal_",
    "linear_init_",
    "conv_init_",
]


def _no_grad_uniform_(tensor, a, b):
    with paddle.no_grad():
        tensor.set_value(
            paddle.uniform(shape=tensor.shape, dtype=tensor.dtype, min=a, max=b)
        )
        return tensor


def _no_grad_normal_(tensor, mean=0.0, std=1.0):
    with paddle.no_grad():
        tensor.set_value(paddle.normal(mean=mean, std=std, shape=tensor.shape))
        return tensor


def _no_grad_trunc_normal_(tensor, mean=0.0, std=1.0, a=2.0, b=2.0):
    # Method based on https://people.sc.fsu.edu/~jburkardt/presentations/truncated_normal.pdf
    def norm_cdf(x):
        # Computes standard normal cumulative distribution function
        return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

    if (mean < a - 2 * std) or (mean > b + 2 * std):
        logger.warning(
            f"mean({mean}) is more than 2 std({std}) from [a, b]([{a}, {b}]) in _no_grad_trunc_normal_. "
            "The distribution of values may be incorrect."
        )
    with paddle.no_grad():
        # Values are generated by using a truncated uniform distribution and
        # then using the inverse CDF for the normal distribution.
        # Get upper and lower cdf values
        l = norm_cdf((a - mean) / std)
        u = norm_cdf((b - mean) / std)

        # Uniformly fill tensor with values from [l, u], then translate to
        # [2l-1, 2u-1].
        _tensor = paddle.uniform(
            shape=tensor.shape, dtype=tensor.dtype, min=2 * l - 1, max=2 * u - 1
        )

        # Use inverse cdf transform for normal distribution to get truncated
        # standard normal
        _tensor.erfinv_()

        # Transform to proper mean, std
        _tensor = paddle.multiply(_tensor, paddle.to_tensor(std * math.sqrt(2.0)))
        _tensor = paddle.add(_tensor, paddle.to_tensor(mean))

        # Clamp to ensure it"s in the proper range
        _tensor = paddle.clip(_tensor, min=a, max=b)
        tensor.set_value(_tensor)
        return tensor


def _no_grad_fill_(tensor, value=0.0):
    with paddle.no_grad():
        tensor.set_value(paddle.full_like(tensor, value, dtype=tensor.dtype))
        return tensor


def uniform_(tensor: paddle.Tensor, a: float, b: float) -> paddle.Tensor:
    """Modify tensor inplace using uniform_.

    Args:
        tensor (paddle.Tensor): Paddle Tensor.
        a (float): min value.
        b (float): max value.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.uniform_(param, -1, 1)
    """
    return _no_grad_uniform_(tensor, a, b)


def normal_(
    tensor: paddle.Tensor, mean: float = 0.0, std: float = 1.0
) -> paddle.Tensor:
    """Modify tensor inplace using normal_.

    Args:
        tensor (paddle.Tensor): Paddle Tensor.
        mean (float, optional): mean value. Defaults to 0.0.
        std (float, optional): std value. Defaults to 1.0.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.normal_(param, 0, 1)
    """
    return _no_grad_normal_(tensor, mean, std)


def trunc_normal_(
    tensor: paddle.Tensor,
    mean: float = 0.0,
    std: float = 1.0,
    a: float = -2.0,
    b: float = 2.0,
) -> paddle.Tensor:
    """Modify tensor inplace using trunc_normal_.

    Args:
        tensor (paddle.Tensor): Paddle Tensor.
        mean (float, optional): The mean of the normal distribution. Defaults to 0.0.
        std (float, optional): The standard deviation of the normal distribution. Defaults to 1.0.
        a (float, optional): The minimum cutoff value. Defaults to -2.0.
        b (float, optional): The maximum cutoff value. Defaults to 2.0.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.trunc_normal_(param, 0.0, 1.0)
    """
    return _no_grad_trunc_normal_(tensor, mean, std, a, b)


def constant_(tensor: paddle.Tensor, value: float = 0.0) -> paddle.Tensor:
    """Modify tensor inplace using constant_.

    Args:
        tensor (paddle.Tensor): Paddle Tensor.
        value (float, optional): value to fill tensor. Defaults to 0.0.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.constant_(param, 2)
    """
    return _no_grad_fill_(tensor, value)


def ones_(tensor: paddle.Tensor) -> paddle.Tensor:
    """Modify tensor inplace using ones_.

    Args:
        tensor (paddle.Tensor): Paddle Tensor.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.ones_(param)
    """
    return _no_grad_fill_(tensor, 1)


def zeros_(tensor: paddle.Tensor) -> paddle.Tensor:
    """Modify tensor inplace using zeros_.

    Args:
        tensor (paddle.Tensor): Paddle Tensor.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.zeros_(param)
    """
    return _no_grad_fill_(tensor, 0)


def _calculate_fan_in_and_fan_out(tensor, reverse=False):
    """
    Calculate (fan_in, _fan_out) for tensor.

    Args:
        tensor (paddle.Tensor): paddle.Tensor.
        reverse (bool): tensor data format order, False by default as [fout, fin, ...].
            e.g. : conv.weight [cout, cin, kh, kw] is False; linear.weight [cin, cout]
            is True.

    Return:
        Tuple[float, float]: (fan_in, fan_out).
    """
    if tensor.ndim < 2:
        raise ValueError(
            f"tensor.ndim should be no less than 2, but got {tensor.ndim}."
        )

    if reverse:
        num_input_fmaps, num_output_fmaps = tensor.shape[0], tensor.shape[1]
    else:
        num_input_fmaps, num_output_fmaps = tensor.shape[1], tensor.shape[0]

    receptive_field_size = 1
    if tensor.ndim > 2:
        receptive_field_size = np.prod(tensor.shape[2:])

    fan_in = num_input_fmaps * receptive_field_size
    fan_out = num_output_fmaps * receptive_field_size

    return fan_in, fan_out


def xavier_uniform_(
    tensor: paddle.Tensor, gain: float = 1.0, reverse: bool = False
) -> paddle.Tensor:
    """Modify tensor inplace using xavier_uniform_.

    Args:
        tensor (paddle.Tensor): Paddle Tensor.
        gain (float, optional): Hyperparameter. Defaults to 1.0.
        reverse (bool, optional): Tensor data format order, False by default as
            [fout, fin, ...].. Defaults to False.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.xavier_uniform_(param)
    """
    fan_in, fan_out = _calculate_fan_in_and_fan_out(tensor, reverse=reverse)
    std = gain * math.sqrt(2.0 / float(fan_in + fan_out))
    k = math.sqrt(3.0) * std
    return _no_grad_uniform_(tensor, -k, k)


def xavier_normal_(
    tensor: paddle.Tensor, gain: float = 1.0, reverse: bool = False
) -> paddle.Tensor:
    """Modify tensor inplace using xavier_normal_.

    Args:
        tensor (paddle.Tensor): Paddle Tensor.
        gain (float, optional): Hyperparameter. Defaults to 1.0.
        reverse (bool, optional): tensor data format order, False by
            default as [fout, fin, ...]. Defaults to False.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.xavier_normal_(param)
    """
    fan_in, fan_out = _calculate_fan_in_and_fan_out(tensor, reverse=reverse)
    std = gain * math.sqrt(2.0 / float(fan_in + fan_out))
    return _no_grad_normal_(tensor, 0, std)


# reference: https://pytorch.org/docs/stable/_modules/torch/nn/init.html
def _calculate_correct_fan(tensor, mode, reverse=False):
    mode = mode.lower()
    valid_modes = ["fan_in", "fan_out"]
    if mode not in valid_modes:
        raise ValueError(f"Mode {mode} not supported, please use one of {valid_modes}")

    fan_in, fan_out = _calculate_fan_in_and_fan_out(tensor, reverse)

    return fan_in if mode == "fan_in" else fan_out


def _calculate_gain(nonlinearity, param=None):
    linear_fns = [
        "linear",
        "conv1d",
        "conv2d",
        "conv3d",
        "conv_transpose1d",
        "conv_transpose2d",
        "conv_transpose3d",
    ]
    if nonlinearity in linear_fns or nonlinearity == "sigmoid":
        return 1
    elif nonlinearity == "tanh":
        return 5.0 / 3
    elif nonlinearity == "relu":
        return math.sqrt(2.0)
    elif nonlinearity == "leaky_relu":
        if param is None:
            negative_slope = 0.01
        elif (
            not isinstance(param, bool)
            and isinstance(param, int)
            or isinstance(param, float)
        ):
            # True/False are instances of int, hence check above
            negative_slope = param
        else:
            raise ValueError(f"negative_slope {param} not a valid number")
        return math.sqrt(2.0 / (1 + negative_slope**2))
    elif nonlinearity == "selu":
        return 3.0 / 4
    else:
        raise ValueError(f"Unsupported nonlinearity {nonlinearity}")


def kaiming_uniform_(
    tensor: paddle.Tensor,
    a: float = 0,
    mode: Literal["fan_in", "fan_out"] = "fan_in",
    nonlinearity: str = "leaky_relu",
    reverse: bool = False,
) -> paddle.Tensor:
    """Modify tensor inplace using kaiming_uniform method.

    Args:
        tensor (paddle.Tensor):  Paddle Tensor.
        a (float, optional): The negative slope of the rectifier used after this layer.
            Defaults to 0.
        mode (Literal[&quot;fan_in&quot;, &quot;fan_out&quot;], optional):
            ["fan_in", "fan_out"]. Defaults to "fan_in".
        nonlinearity (str, optional): Nonlinearity method name. Defaults to "leaky_relu".
        reverse (bool, optional): tensor data format order, False by default as
            [fout, fin, ...].. Defaults to False.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.kaiming_uniform_(param)
    """
    fan = _calculate_correct_fan(tensor, mode, reverse)
    gain = _calculate_gain(nonlinearity, a)
    std = gain / math.sqrt(fan)
    k = math.sqrt(3.0) * std
    return _no_grad_uniform_(tensor, -k, k)


def kaiming_normal_(
    tensor: paddle.Tensor,
    a: float = 0,
    mode: Literal["fan_in", "fan_out"] = "fan_in",
    nonlinearity: str = "leaky_relu",
    reverse: bool = False,
) -> paddle.Tensor:
    """Modify tensor inplace using kaiming_normal_.

    Args:
        tensor (paddle.Tensor): Paddle Tensor.
        a (float, optional): The negative slope of the rectifier used after this layer.
            Defaults to 0.
        mode (Literal[&quot;fan_in&quot;, &quot;fan_out&quot;], optional): Either
            'fan_in' (default) or 'fan_out'. Defaults to "fan_in".
        nonlinearity (str, optional): Nonlinearity method name. Defaults to "leaky_relu".
        reverse (bool, optional): Tensor data format order. Defaults to False.

    Returns:
        paddle.Tensor: Initialized tensor.

    Examples:
        >>> import paddle
        >>> import ppsci
        >>> param = paddle.empty((128, 256), "float32")
        >>> param = ppsci.utils.initializer.kaiming_normal_(param)
    """
    fan = _calculate_correct_fan(tensor, mode, reverse)
    gain = _calculate_gain(nonlinearity, a)
    std = gain / math.sqrt(fan)
    return _no_grad_normal_(tensor, 0, std)


def linear_init_(module: nn.Layer) -> None:
    """Initialize module's weight and bias as it is a linear layer.

    Args:
        module (nn.Layer): Linear Layer to be initialized.
    """
    bound = 1 / math.sqrt(module.weight.shape[0])
    uniform_(module.weight, -bound, bound)
    if module.bias is not None:
        uniform_(module.bias, -bound, bound)


def conv_init_(module: nn.Layer) -> None:
    """Initialize module's weight and bias as it is a conv layer.

    Args:
        module (nn.Layer): Convolution Layer to be initialized.
    """
    bound = 1 / np.sqrt(np.prod(module.weight.shape[1:]))
    uniform_(module.weight, -bound, bound)
    if module.bias is not None:
        uniform_(module.bias, -bound, bound)
