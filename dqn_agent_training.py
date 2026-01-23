import numpy as np
import random
import torch
import torch.nn as nn
import torch.optim as optim


class SimpleGameEnvironment:
    """
    Simple game: Agent must reach target position on a 1D line.
    State: [agent_pos, target_pos] (normalized to 0-1)
    Actions: 0=left, 1=stay, 2=right
    """
    def __init__(self, grid_size=10):
        self.grid_size = grid_size
        self.agent_pos = 0
        self.target_pos = 0
        self.max_steps = 50
        self.current_step = 0
        
    def reset(self):
        self.agent_pos = random.randint(0, self.grid_size - 1)
        self.target_pos = random.randint(0, self.grid_size - 1)
        while self.target_pos == self.agent_pos:
            self.target_pos = random.randint(0, self.grid_size - 1)
        self.current_step = 0
        return self._get_state()
    
    def _get_state(self) -> np.ndarray:
        return np.array([
            self.agent_pos / self.grid_size,
            self.target_pos / self.grid_size,
            (self.target_pos - self.agent_pos) / self.grid_size  # direction hint
        ], dtype=np.float32)
    
    def get_valid_actions(self):
        actions = [1]  # stay is always valid
        if self.agent_pos > 0:
            actions.append(0)  # left
        if self.agent_pos < self.grid_size - 1:
            actions.append(2)  # right
        return actions
    
    def step(self, action):
        self.current_step += 1
        
        # Execute action
        if action == 0 and self.agent_pos > 0:
            self.agent_pos -= 1
        elif action == 2 and self.agent_pos < self.grid_size - 1:
            self.agent_pos += 1
        # action 1 = stay, do nothing
        
        # Calculate reward
        if self.agent_pos == self.target_pos:
            reward = 10.0  # reached target
            done = True
        elif self.current_step >= self.max_steps:
            reward = -1.0  # timeout
            done = True
        else:
            # Small reward for getting closer
            distance = abs(self.target_pos - self.agent_pos)
            reward = -0.1 - (distance / self.grid_size) * 0.1
            done = False
            
        return self._get_state(), reward, done, {}


class PrioritizedReplayBuffer:
    def __init__(self, capacity, alpha=0.6, beta_start=0.4, beta_frames=100000):
        self.capacity = capacity
        self.alpha = alpha
        self.beta_start = beta_start
        self.beta_frames = beta_frames
        self.frame = 1
        self.buffer = []
        self.priorities = np.zeros(capacity, dtype=np.float32)
        self.position = 0
        
    def beta_by_frame(self):
        return min(1.0, self.beta_start + (1.0 - self.beta_start) * self.frame / self.beta_frames)
    
    def __len__(self):
        return len(self.buffer)
        
    def add(self, *transition, priority=None):
        max_priority = self.priorities.max() if self.buffer else 1.0
        if priority is None:
            priority = max_priority
            
        if len(self.buffer) < self.capacity:
            self.buffer.append(transition)
        else:
            self.buffer[self.position] = transition
            
        self.priorities[self.position] = priority + 1e-6  # avoid zero priority
        self.position = (self.position + 1) % self.capacity
        
    def sample(self, batch_size):
        if len(self.buffer) == self.capacity:
            priorities = self.priorities
        else:
            priorities = self.priorities[:len(self.buffer)]
            
        probabilities = priorities ** self.alpha
        probabilities /= probabilities.sum()
        
        indices = np.random.choice(len(self.buffer), batch_size, p=probabilities)
        samples = [self.buffer[idx] for idx in indices]
        
        weights = (len(self.buffer) * probabilities[indices]) ** (-self.beta_by_frame())
        weights /= weights.max()
        
        self.frame += 1
        return samples, indices, weights
    
    def update_priorities(self, indices, priorities):
        for idx, priority in zip(indices, priorities):
            p = priority.item() if hasattr(priority, 'item') else float(priority)
            self.priorities[idx] = abs(p) + 1e-6


class SimpleDQN(nn.Module):
    def __init__(self, state_size, action_size):
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(state_size, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, action_size)
        )
        
    def forward(self, x):
        return self.model(x)


class DQNAgent:
    TARGET_UPDATE_EVERY = 100

    def __init__(self, state_size: int, action_size: int, device: str = "cpu",
                 epsilon: float = 1.0, epsilon_min: float = 0.01, epsilon_decay: float = 0.995):
        self.state_size = state_size
        self.action_size = action_size
        self.device = torch.device(device)

        self.memory = PrioritizedReplayBuffer(capacity=10000)
        self.gamma = 0.99
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.learning_rate = 1e-3

        self.model = SimpleDQN(state_size, action_size).to(self.device)
        self.target_model = SimpleDQN(state_size, action_size).to(self.device)
        self.update_target_model()

        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        self._step_count = 0

    def act(self, state: np.ndarray, valid_actions: list[int]):
        if random.random() < self.epsilon:
            return random.choice(valid_actions)

        state_t = torch.from_numpy(state).float().unsqueeze(0).to(self.device)

        with torch.no_grad():
            q_vals = self.model(state_t)[0]
            q_vals_masked = q_vals.clone()
            for i in range(self.action_size):
                if i not in valid_actions:
                    q_vals_masked[i] = -float('inf')
            return torch.argmax(q_vals_masked).item()

    def memorize(self, state, action, reward, next_state, done):
        self.memory.add(state, action, reward, next_state, done)

    def replay(self, batch_size: int = 32):
        if len(self.memory) < batch_size:
            return

        samples, indices, weights = self.memory.sample(batch_size)
        states, actions, rewards, next_states, dones = zip(*samples)

        states = torch.as_tensor(np.array(states), dtype=torch.float32, device=self.device)
        actions = torch.as_tensor(actions, dtype=torch.int64, device=self.device).unsqueeze(1)
        rewards = torch.as_tensor(rewards, dtype=torch.float32, device=self.device).unsqueeze(1)
        next_states = torch.as_tensor(np.array(next_states), dtype=torch.float32, device=self.device)
        dones = torch.as_tensor(dones, dtype=torch.float32, device=self.device).unsqueeze(1)
        weights = torch.as_tensor(weights, dtype=torch.float32, device=self.device).unsqueeze(1)

        q_sa = self.model(states).gather(1, actions)

        with torch.no_grad():
            q_next_max = self.target_model(next_states).max(1, keepdim=True)[0]
            y = rewards + self.gamma * q_next_max * (1 - dones)

        td_error = torch.abs(q_sa - y).detach()
        self.memory.update_priorities(indices, td_error.squeeze().cpu().numpy())

        loss = (weights * (q_sa - y) ** 2).mean()

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()

        self._step_count += 1
        if self._step_count % self.TARGET_UPDATE_EVERY == 0:
            self.update_target_model()

    def update_target_model(self):
        self.target_model.load_state_dict(self.model.state_dict())

    def decay_epsilon(self):
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay


def train_and_test():
    print("=== Simple DQN Test ===\n")
    
    env = SimpleGameEnvironment(grid_size=10)
    state_size = 3  # [agent_pos, target_pos, direction]
    action_size = 3  # left, stay, right
    
    agent = DQNAgent(state_size, action_size, device="cpu")
    
    episodes = 500
    batch_size = 32
    
    rewards_history = []
    
    for ep in range(episodes):
        state = env.reset()
        ep_reward = 0
        
        while True:
            valid_actions = env.get_valid_actions()
            action = agent.act(state, valid_actions)
            next_state, reward, done, _ = env.step(action)
            
            agent.memorize(state, action, reward, next_state, done)
            agent.replay(batch_size)
            
            state = next_state
            ep_reward += reward
            
            if done:
                agent.decay_epsilon()
                rewards_history.append(ep_reward)
                break
        
        if (ep + 1) % 50 == 0:
            avg_reward = np.mean(rewards_history[-50:])
            print(f"Episode {ep+1:4d} | Avg Reward (last 50): {avg_reward:7.2f} | Epsilon: {agent.epsilon:.3f}")
    
    # Test the trained agent
    print("\n=== Testing Trained Agent ===\n")
    agent.epsilon = 0  # No exploration
    
    for test_ep in range(5):
        state = env.reset()
        print(f"Test {test_ep+1}: Start pos={int(env.agent_pos)}, Target={int(env.target_pos)}")
        steps = 0
        
        while True:
            valid_actions = env.get_valid_actions()
            action = agent.act(state, valid_actions)
            next_state, reward, done, _ = env.step(action)
            state = next_state
            steps += 1
            
            if done:
                success = "SUCCESS" if env.agent_pos == env.target_pos else "TIMEOUT"
                print(f"  -> {success} in {steps} steps (final pos={int(env.agent_pos)})\n")
                break
    
    print("Test complete!")


if __name__ == "__main__":
    train_and_test()