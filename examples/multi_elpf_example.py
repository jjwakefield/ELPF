from datetime import datetime, timedelta

import numpy as np
from scipy.stats import multivariate_t, uniform
from tqdm import tqdm

from ELPF.array_type import StateVector
from ELPF.detection import Clutter, TrueDetection
from ELPF.filter import ExpectedLikelihoodParticleFilter
from ELPF.hypothesise import JPDAHypothesiser
from ELPF.measurement import CartesianToRangeBearingMeasurementModel
from ELPF.plotting import AnimatedPlot
from ELPF.state import GroundTruthPath, GroundTruthState, Particle, ParticleState, State, Track
from ELPF.transition import CombinedLinearGaussianTransitionModel, ConstantVelocity

if __name__ == "__main__":
    # Set random seed
    np.random.seed(1999)

    # Define the mapping between the state vector and the measurement space
    mapping = (0, 2)

    # Create the ground truth transition model
    process_noise = 0.0
    transition_model = CombinedLinearGaussianTransitionModel(
        [ConstantVelocity(process_noise), ConstantVelocity(process_noise)]
    )

    # Create the measurement model
    measurement_noise = np.diag([1, np.deg2rad(0.2)])  # Noise covariance for range and bearing
    translation_offset = np.array([[0], [0]])
    measurement_model = CartesianToRangeBearingMeasurementModel(
        measurement_noise, mapping, translation_offset
    )

    # Number of steps
    num_steps = 100

    # Start time
    start_time = datetime.now().replace(microsecond=0)
    time_interval = timedelta(seconds=1)
    timesteps = [start_time]

    # Generate ground truth
    truths = [
        GroundTruthPath(GroundTruthState([-10, 0.25, -10, 0.50], timestamp=start_time)),
        GroundTruthPath(GroundTruthState([-10, 0.25, 20, -0.50], timestamp=start_time)),
        GroundTruthPath(GroundTruthState([10, -0.25, 20, -0.50], timestamp=start_time)),
    ]
    for i in range(1, num_steps):
        for truth in truths:
            truth.append(
                GroundTruthState(
                    transition_model.function(truth[-1], time_interval),
                    timestamp=timesteps[-1],
                )
            )
        timesteps.append(start_time + i * time_interval)

    # Clutter parameters
    clutter_rate = 2
    x_min = min(state.state_vector[0, 0] for truth in truths for state in truth)
    x_max = max(state.state_vector[0, 0] for truth in truths for state in truth)
    y_min = min(state.state_vector[2, 0] for truth in truths for state in truth)
    y_max = max(state.state_vector[2, 0] for truth in truths for state in truth)
    surveillance_area = (x_max - x_min) * (y_max - y_min)
    clutter_spatial_density = clutter_rate / surveillance_area

    prob_detect = 0.95  # 95% chance of detection

    # Generate the measurements
    all_measurements = []
    for k in range(num_steps):
        measurement_set = set()

        for truth in truths:
            # Generate actual detection from the state with a chance of missed detection
            if np.random.rand() < prob_detect:
                measurement = measurement_model.function(truth[k], noise=True)
                measurement_set.add(
                    TrueDetection(
                        state_vector=measurement,
                        timestamp=truth[k].timestamp,
                        measurement_model=measurement_model,
                    )
                )

        # Generate clutter with Poisson number of clutter points
        for _ in range(np.random.poisson(clutter_rate)):
            x = uniform.rvs(x_min, x_max - x_min)
            y = uniform.rvs(y_min, y_max - y_min)
            clutter = StateVector(
                measurement_model.function(
                    State(StateVector([x, 0, y, 0]), truth[k].timestamp), noise=False
                )
            )
            measurement_set.add(
                Clutter(clutter, measurement_model=measurement_model, timestamp=truth[k].timestamp)
            )

        all_measurements.append(measurement_set)

    # Define number of particles
    num_particles = 1000

    # Create prior states for the tracks
    tracks = []
    for truth in truths:
        state_vector = truth[0].state_vector.flatten()
        samples = np.random.multivariate_normal(
            mean=state_vector, cov=np.diag([15, 0.5, 15, 0.5]), size=num_particles
        )
        weights = np.ones(num_particles) / num_particles
        particles = np.array(
            [Particle(sample, weight) for sample, weight in zip(samples, weights)]
        )
        prior = ParticleState(particles, timestamp=start_time)
        tracks.append(Track([prior]))

    # Define likelihood function and its arguments
    likelihood_func = multivariate_t.pdf
    likelihood_func_kwargs = {"shape": measurement_model.covar, "df": measurement_model.covar.ndim}

    # Create the particle filter transition model
    process_noise = 0.1
    transition_model = CombinedLinearGaussianTransitionModel(
        [ConstantVelocity(process_noise), ConstantVelocity(process_noise)]
    )

    # Create the ELPF
    pf = ExpectedLikelihoodParticleFilter(transition_model, measurement_model)

    # Create hypothesiser
    hypothesiser = JPDAHypothesiser(
        measurement_model=measurement_model,
        detection_probability=prob_detect,
        clutter_spatial_density=clutter_spatial_density,
        likelihood_function=likelihood_func,
        likelihood_function_args=likelihood_func_kwargs,
        gate_probability=0.95,
        include_all=False,
    )

    # Perform the particle filtering
    for measurements in tqdm(all_measurements, desc="Filtering"):
        priors = [pf.predict(track[-1], time_interval) for track in tracks]

        hypotheses = hypothesiser.hypothesise(priors, measurements)

        for i, track in enumerate(tracks):
            post = pf.update(priors[i], hypotheses[priors[i]])
            track.append(post)

    # Plot the results
    plotter = AnimatedPlot(timesteps, tail_length=1)
    plotter.plot_truths(truths, mapping=mapping)
    plotter.plot_measurements(all_measurements)
    plotter.plot_tracks(tracks, mapping=mapping, plot_particles=True)
    plotter.show()