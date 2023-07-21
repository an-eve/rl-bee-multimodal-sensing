import os
import argparse
import yaml
import numpy as np
import torch.nn as nn
import gymnasium as gym
from bee import BeeWorld
from utils import create_directory
from stable_baselines3 import TD3
from stable_baselines3.common.noise import (
    NormalActionNoise,
    # OrnsteinUhlenbeckActionNoise
)
from stable_baselines3.common.callbacks import (
    EvalCallback,
    StopTrainingOnNoModelImprovement,
)
from stable_baselines3.common.logger import configure
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv


def init_gym(gym_name, render_mode="rgb_array", max_episode_steps=1000, logs_path=None):
    """Initialise the gym environment with given setup"""
    gym.register(
        id=gym_name,
        entry_point=BeeWorld,
        max_episode_steps=max_episode_steps,
    )
    env = gym.make(gym_name, render_mode=render_mode)

    if logs_path:
        env = Monitor(env, logs_path, allow_early_resets=True)
    env.reset()

    return env


def init_model(
    env,
    policy_kwargs={
        "net_arch": [100, 100],
        "activation_fn": nn.ReLU,
    },
    learning_rate=0.01,
    logger=None,
):
    """Initialise the model with given setup"""
    n_actions = env.action_space.shape[-1]
    action_noise = NormalActionNoise(
        mean=np.zeros(n_actions), sigma=0.1 * np.ones(n_actions)
    )

    model = TD3(
        "MultiInputPolicy",
        env,
        action_noise=action_noise,
        verbose=1,
        policy_kwargs=policy_kwargs,
        learning_rate=learning_rate,
    )

    if logger:
        model.set_logger(logger)

    return model


def setup_logging(env, logs_path, best_model_save_path):
    logger = configure(logs_path, ["stdout", "csv", "log", "tensorboard", "json"])
    stop_train_callback = StopTrainingOnNoModelImprovement(
        max_no_improvement_evals=3, min_evals=5, verbose=1
    )
    """Set up the logger and early stopping callback"""
    eval_callback = EvalCallback(
        env,
        callback_after_eval=stop_train_callback,
        best_model_save_path=best_model_save_path,
        log_path=logs_path,
        eval_freq=1000,
        n_eval_episodes=10,
        deterministic=True,
        render=False,
    )
    return eval_callback, logger


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the RL model.")
    parser.add_argument(
        "--config_path",
        type=str,
        default="config.yaml",
        help="config file for your model",
    )
    args = parser.parse_args()

    with open(args.config_path, "r") as file:
        config = yaml.safe_load(file)

    config["train"]["policy_kwargs"]["activation_fn"] = getattr(
        nn, config["train"]["policy_kwargs"]["activation_fn"]
    )

    base_path = config["setup"]["path"]
    logs_path = base_path + "logs/"
    replay_buffer_path = base_path + "replay_buffer"

    gym_name = config["setup"]["gym_name"]
    policy_kwargs = config["train"]["policy_kwargs"]
    learning_rate = config["train"]["learning_rate"]
    timesteps = config["train"]["timesteps"]

    if os.path.exists(base_path):
        print("Loading existing model:", base_path)
        model = TD3.load(base_path + "best_model")
        env = init_gym(gym_name, logs_path=logs_path)
        model.set_env(DummyVecEnv([lambda: env]))
        model.load_replay_buffer(replay_buffer_path)
        callback, logger = setup_logging(env, logs_path, base_path)

    else:
        create_directory(logs_path)

        env = init_gym(gym_name, logs_path=logs_path)
        callback, logger = setup_logging(env, logs_path, base_path)
        model = init_model(env, policy_kwargs, learning_rate, logger=logger)

    model.learn(
        total_timesteps=timesteps,
        reset_num_timesteps=False,
        callback=callback,
    )
    model.save_replay_buffer(replay_buffer_path)

    env.close()
