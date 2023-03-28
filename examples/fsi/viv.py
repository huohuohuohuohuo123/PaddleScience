"""Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import random

import numpy as np
import paddle
import paddle.amp as amp
import paddle.distributed as dist
from packaging import version
from paddle.distributed import fleet

import ppsci
from ppsci.utils import logger
from ppsci.utils import misc
from ppsci.utils import save_load


def train(solver: ppsci.solver.Solver):
    # init hyper-parameters
    epochs = 100000
    solver.cfg = {
        "profiler_options": None,
        "Global": {"epochs": epochs},
        "Arch": {"name": "MLP"},
    }
    solver.iters_per_epoch = 1
    save_freq = 1000
    eval_during_train = True
    eval_freq = 1000
    start_eval_epoch = 1

    # init gradient accumulation config
    solver.update_freq = 1

    best_metric = {
        "metric": float("inf"),
        "epoch": 0,
    }

    # load pretrained model if specified
    pretrained_model_path = None
    if pretrained_model_path is not None:
        save_load.load_pretrain(solver.model, pretrained_model_path)

    # init optimizer and lr scheduler
    solver.lr_scheduler = ppsci.optimizer.lr_scheduler.Step(
        epochs, solver.iters_per_epoch, 0.001, step_size=20000, gamma=0.9
    )()
    solver.optimizer = ppsci.optimizer.Adam(solver.lr_scheduler)(
        [solver.model] + list(solver.equation.values())
    )

    # load checkpoint for resume training
    checkpoint_path = None
    if checkpoint_path is not None:
        loaded_metric = save_load.load_checkpoint(
            "checkpoint_path", solver.model, solver.optimizer
        )
        if isinstance(loaded_metric, dict):
            best_metric.update(loaded_metric)

    # maunally build constraint(s)
    solver.constraints = {
        "Sup": ppsci.constraint.SupervisedConstraint(
            "VIV_Training_Neta100.mat",
            ["t_f"],
            solver.equation["VIV"].equations,
            {},
            {
                "dataset": "NamedArrayDataset",
                "iters_per_epoch": solver.iters_per_epoch,
                "sampler": {
                    "name": "BatchSampler",
                    "batch_size": 150,
                    "drop_last": False,
                    "shuffle": True,
                },
                "num_workers": 2,
                "seed": 42,
                "use_shared_memory": False,
            },
            ppsci.loss.MSELoss("mean"),
            weight_dict={
                "eta": 100,
            },
            name="EQ",
        ),
    }

    # init train output infor object
    solver.train_output_info = {}
    solver.train_time_info = {
        "batch_cost": misc.AverageMeter("batch_cost", ".5f", postfix="s"),
        "reader_cost": misc.AverageMeter("reader_cost", ".5f", postfix="s"),
    }

    # init train func
    solver.train_mode = None
    if solver.train_mode is None:
        solver.train_epoch_func = ppsci.solver.train.train_epoch_func
    else:
        solver.train_epoch_func = ppsci.solver.train.train_LBFGS_epoch_func

    # init distributed environment
    if solver.world_size > 1:
        # TODO(sensen): support different kind of DistributedStrategy
        fleet.init(is_collective=True)
        solver.model = fleet.distributed_model(solver.model)
        solver.optimizer = fleet.distributed_optimizer(solver.optimizer)

    # train epochs
    solver.global_step = 0
    for epoch_id in range(1, epochs + 1):
        solver.train_epoch_func(solver, epoch_id, solver.log_freq)

        # log training summation at end of a epoch
        metric_msg = ", ".join(
            [solver.train_output_info[key].avg_info for key in solver.train_output_info]
        )
        logger.info(f"[Train][Epoch {epoch_id}/{epochs}][Avg] {metric_msg}")
        solver.train_output_info.clear()

        cur_metric = float("inf")
        # evaluate during training
        if (
            eval_during_train
            and epoch_id % eval_freq == 0
            and epoch_id >= start_eval_epoch
        ):
            cur_metric = eval(solver, epoch_id)
            if cur_metric < best_metric["metric"]:
                best_metric["metric"] = cur_metric
                best_metric["epoch"] = epoch_id
                save_load.save_checkpoint(
                    solver.model,
                    solver.optimizer,
                    best_metric,
                    solver.output_dir,
                    solver.model.__class__.__name__,
                    "best_model",
                )
            logger.info(
                f"[Eval][Epoch {epoch_id}][best metric: {best_metric['metric']}]"
            )
            logger.scaler("eval_metric", cur_metric, epoch_id, solver.vdl_writer)

        # update learning rate by epoch
        if solver.lr_scheduler.by_epoch:
            solver.lr_scheduler.step()

        # save epoch model every `save_freq`
        if save_freq > 0 and epoch_id % save_freq == 0:
            save_load.save_checkpoint(
                solver.model,
                solver.optimizer,
                {"metric": cur_metric, "epoch": epoch_id},
                solver.output_dir,
                solver.model.__class__.__name__,
                f"epoch_{epoch_id}",
            )

        # always save the latest model for convenient resume training
        save_load.save_checkpoint(
            solver.model,
            solver.optimizer,
            {"metric": cur_metric, "epoch": epoch_id},
            solver.output_dir,
            solver.model.__class__.__name__,
            "latest",
        )

    # close VisualDL
    if solver.vdl_writer is not None:
        solver.vdl_writer.close()


def eval(solver: ppsci.solver.Solver, epoch_id):
    """Evaluation"""
    if not hasattr(solver, "cfg"):
        solver.cfg = {
            "profiler_options": None,
            "Global": {"epochs": 0},
            "Arch": {"name": "MLP"},
        }
    if not hasattr(solver, "global_step"):
        solver.global_step = 0

    # load pretrained model if specified
    pretrained_model_path = None
    if pretrained_model_path is not None:
        save_load.load_pretrain(solver.model, pretrained_model_path)

    solver.model.eval()

    # init train func
    solver.eval_func = ppsci.solver.eval.eval_func

    # init validator(s) at the first time
    if not hasattr(solver, "validator"):
        solver.validator = {
            "eta_mse": ppsci.validate.CSVValidator(
                "./VIV_Training_Neta100.mat",
                ["t_f"],
                ["eta"],
                {},
                {
                    "dataset": "NamedArrayDataset",
                    "total_size": 100,
                    "sampler": {
                        "name": "BatchSampler",
                        "batch_size": 32,
                        "drop_last": False,
                        "shuffle": False,
                    },
                    "num_workers": 0,
                    "seed": 42,
                    "use_shared_memory": False,
                },
                ppsci.loss.MSELoss("mean"),
                metric={"MSE": ppsci.metric.MSE()},
                name="eta_mse",
            )
        }

    solver.eval_output_info = {}
    solver.eval_time_info = {
        "batch_cost": misc.AverageMeter("batch_cost", ".5f", postfix="s"),
        "reader_cost": misc.AverageMeter("reader_cost", ".5f", postfix="s"),
    }

    # do evaluation
    result = solver.eval_func(solver, epoch_id, solver.log_freq)

    # log evaluation summation
    metric_msg = ", ".join(
        [solver.eval_output_info[key].avg_info for key in solver.eval_output_info]
    )
    logger.info(f"[Eval][Epoch {epoch_id}] {metric_msg}")
    solver.eval_output_info.clear()

    solver.model.train()
    return result


if __name__ == "__main__":
    # initialzie hyper-parameter, geometry, model, equation and AMP settings
    solver = ppsci.solver.Solver()
    solver.mode = "train"
    solver.rank = dist.get_rank()
    solver.vdl_writer = None

    # set seed
    paddle.seed(42 + solver.rank)
    np.random.seed(42 + solver.rank)
    random.seed(42 + solver.rank)

    # set output diretory
    solver.output_dir = "./output_viv"

    # initialize logger
    solver.log_freq = 10
    logger.init_logger(log_file=f"./{solver.output_dir}/{solver.mode}.log")

    # set device
    solver.device = paddle.set_device("gpu")

    # log paddlepaddle's version
    paddle_version = (
        paddle.__version__
        if version.Version(paddle.__version__) != version.Version("0.0.0")
        else f"develop({paddle.version.commit[:7]})"
    )
    logger.info(f"Using paddlepaddle {paddle_version} on device {solver.device}")

    # manually init geometry(ies)
    solver.geom = {}

    # manually init model
    solver.model = ppsci.arch.MLP(["t_f"], ["eta"], 5, 50, "tanh", False, False)

    # manually init equation(s)
    solver.equation = {"VIV": ppsci.equation.Vibration(2, -4, 0)}

    # init AMP
    solver.use_amp = False
    if solver.use_amp:
        solver.amp_level = "O1"
        solver.scaler = amp.GradScaler(True, 2**16)
    else:
        solver.amp_level = "O0"

    solver.world_size = dist.get_world_size()

    # manually start training
    if solver.mode == "train":
        train(solver)
    # manually start evaluation
    elif solver.mode == "eval":
        eval(solver, 0)
