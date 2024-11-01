from datetime import datetime

import numpy as np
from scipy.stats import uniform
from tqdm import tqdm

from ELPF.detection import Clutter, TrueDetection
from ELPF.likelihood import t_pdf
from ELPF.measurement import CartesianToRangeBearingMeasurementModel
from ELPF.particle_filter import ExpectedLikelihoodParticleFilter
from ELPF.plotting import plot
from ELPF.state import Particle, ParticleState, State
from ELPF.transition import CombinedLinearGaussianTransitionModel, ConstantVelocity

if __name__ == "__main__":
    # Set random seed
    np.random.seed(1999)

    # Define the mapping between the state vector and the measurement space
    mapping = (0, 2)

    # Create the transition model
    time_interval = 1
    process_noise = 0.005
    transition_model = CombinedLinearGaussianTransitionModel(
        [ConstantVelocity(process_noise), ConstantVelocity(process_noise)]
    )

    # Create the measurement model
    measurement_noise = np.diag([1, np.deg2rad(0.2)])  # Noise covariance for range and bearing
    measurement_model = CartesianToRangeBearingMeasurementModel(measurement_noise, mapping)

    # Number of steps
    num_steps = 100

    # Generate ground truth
    truth = [State(np.array([100, 1, 100, 1]))]
    for _ in range(1, num_steps):
        state = transition_model.function(truth[-1], time_interval)
        truth.append(State(state))

    prob_detect = 0.8  # 80% chance of detection

    # Generate measurements
    all_measurements = []
    for state in truth:
        measurement_set = set()

        # Generate detection with probability prob_detect
        if np.random.rand() <= prob_detect:
            measurement = measurement_model.function(state, noise=True)
            measurement_set.add(
                TrueDetection(state_vector=measurement, measurement_model=measurement_model)
            )

        # Generate clutter with Poisson number of clutter points
        truth_x = state.state_vector[mapping[0]]
        truth_y = state.state_vector[mapping[1]]
        for _ in range(np.random.poisson(5)):
            x = uniform.rvs(truth_x - 10, 40)
            y = uniform.rvs(truth_y - 10, 40)
            clutter = measurement_model.function(State(np.array([x, 0, y, 0])), noise=False)
            measurement_set.add(
                Clutter(
                    clutter,
                    measurement_model=measurement_model,
                )
            )

        all_measurements.append(measurement_set)

    # Define number of particles
    num_particles = 1000

    # Create a prior state
    samples = np.random.multivariate_normal(
        mean=[100, 1, 100, 1], cov=np.diag([1.5, 0.5, 1.5, 0.5]), size=num_particles
    )

    weights = np.ones(num_particles) / num_particles
    particles = np.array([Particle(sample, weight) for sample, weight in zip(samples, weights)])
    prior = ParticleState(particles)

    # Create a particle filter
    pf = ExpectedLikelihoodParticleFilter(transition_model, measurement_model, t_pdf)

    # Create a track to store the state estimates
    track = [prior]

    start_time = datetime.now().replace(microsecond=0)

    # Perform the particle filtering
    for measurements in tqdm(all_measurements, desc="Filtering"):
        # Predict the new state
        prior = pf.predict(track[-1], time_interval)

        # Update the state
        posterior = pf.update(prior, measurements)

        track.append(posterior)

    end_time = datetime.now().replace(microsecond=0)

    runtime = end_time - start_time
    print(f"Runtime: {runtime}")

    # Plot the results
    plot(track, truth, all_measurements, mapping, save=False)
