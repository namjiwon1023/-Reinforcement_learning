import gym
import numpy as np
from PPO import PPOAgent
from utils import plot_learning_curve

if __name__ == '__main__':
    # env = gym.make('Pendulum-v0')
    env = gym.make('LunarLander-v2')
    N = 20
    batch_size = 5
    n_epochs = 4
    alpha = 3e-4
    input_dims = env.observation_space.shape[0]
    # n_actions = env.action_space.shape[0]
    # print(env.action_space.shape[0])
    # agent = PPOAgent(input_dims, n_actions, 0.99, alpha, 0.95, 0.2, batch_size, 2048, 4)
    agent = PPOAgent(input_dims, 3, 0.99, alpha, 0.95, 0.2, batch_size, 2048, 4)
    n_games = int(1e6)
    figure_file = '/home/nam/Reinforcement_learning/GAE_PPO_continuous_test/LunarLander.png'
    # print('reward_range[0] : ',env.reward_range[0])
    best_score = env.reward_range[0]
    score_history = []

    # max_action = float(env.action_space.high[0])
    # print('max_action : ',max_action)

    learn_iters = 0
    avg_score = 0
    n_steps = 0

    for i in range(n_games):
        observation = env.reset()
        done = False
        score = 0
        while not done:
            env.render()
            action, prob, val = agent.choose_action(observation)
            # print('action:',action)
            observation_, reward, done, info = env.step(action)
            n_steps += 1
            score += reward
            agent.remember(observation, action, prob, val, reward, done)
            if n_steps % N == 0:
                agent.learn()
                learn_iters += 1
            observation = observation_
        score_history.append(score)
        avg_score = np.mean(score_history[-100:])

        if avg_score > best_score:
            best_score = avg_score
            agent.save_models()

        print('episode',i,'score %.1f' %score,'avg score %.1f' % avg_score, 'time_steps',n_steps, 'learning_ step',learn_iters)

    x = [i+1 for i in range(len(score_history))]
    plot_learning_curve(x, score_history, figure_file)