import numpy as np

from ELPF.state import Particle, ParticleState


class ParticleFilter:
    def __init__(self, transition_model, measurement_model, likelihood_function):
        """
        Initialises the Particle Filter with a given transition and measurement model.

        Parameters
        ----------
        transition_model : TransitionModel
            The model used to predict the next state based on the current state.
        measurement_model : MeasurementModel
            The model used to convert states to measurements and vice versa.
        """
        self.transition_model = transition_model
        self.measurement_model = measurement_model
        self.likelihood_function = likelihood_function

    def predict(self, particle_state: ParticleState, time_interval: float) -> ParticleState:
        """
        Predicts the next state of each particle based on the transition model.

        Parameters
        ----------
        particle_state : ParticleState
            The current state of the particles.
        time_interval : float
            The time interval for the transition model.

        Returns
        -------
        ParticleState
            The predicted state of the particles after applying the transition model.
        """
        new_states = self.transition_model.function(particle_state, time_interval)
        return ParticleState(
            [
                Particle(state, particle.weight)
                for state, particle in zip(new_states.T, particle_state.particles)
            ]
        )

    def resample(self, particle_state: ParticleState) -> ParticleState:
        """
        Resamples particles based on their weights if the Effective Sample Size (ESS) is below
        a threshold.

        Parameters
        ----------
        particle_state : ParticleState
            The current state of the particles.

        Returns
        -------
        ParticleState
            The resampled particle state, or the original state if no resampling is needed.
        """
        num_particles = particle_state.num_particles
        ess = 1 / np.sum(particle_state.weights**2)

        if ess < (num_particles / 2):
            weights = particle_state.weights
            cdf = np.cumsum(weights)
            cdf[-1] = 1.0  # Ensure last value is 1.0
            u_i = np.random.uniform(0, 1 / num_particles)
            u_j = u_i + (1 / num_particles) * np.arange(num_particles)
            index = np.searchsorted(cdf, u_j)

            # Create new particles based on the resampled indices
            new_state_vector = particle_state.state_vector[:, index]
            new_particles = [
                Particle(state_vector, 1.0 / num_particles) for state_vector in new_state_vector.T
            ]

            return ParticleState(new_particles)
        return particle_state


class BootstrapParticleFilter(ParticleFilter):

    def update(self, particle_state: ParticleState, measurement: np.ndarray) -> ParticleState:
        """
        Updates the particle weights based on the measurement and resamples if necessary.

        Parameters
        ----------
        particle_state : ParticleState
            The current state of the particles.
        measurement : np.ndarray
            The measurement received from the environment.

        Returns
        -------
        ParticleState
            The updated particle state after incorporating the measurement.
        """
        # new_particles = []
        # for particle in particle_state.particles:
        #     # Predict measurement
        #     predicted_measurement = self.measurement_model.function(particle, noise=False)

        #     # Calculate the likelihood using the Gaussian PDF
        #     likelihood = self.likelihood_function(
        #         measurement.state_vector, predicted_measurement, self.measurement_model.covar
        #     )

        #     # Update the particle's weight
        #     new_particles.append(Particle(particle.state_vector, particle.weight * likelihood))

        predicted_measurements = self.measurement_model.function(particle_state, noise=False)

        # Calculate likelihoods of each particle for the measurement
        likelihoods = self.likelihood_function(
            measurement.state_vector, predicted_measurements, self.measurement_model.covar
        )

        weights = np.array([particle.weight for particle in particle_state.particles])
        new_weights = weights * likelihoods

        # Create new particles with updated weights
        new_particles = [
            Particle(particle.state_vector, new_weight)
            for particle, new_weight in zip(particle_state.particles, new_weights)
        ]

        # Normalise weights to sum to 1
        total_weight = np.sum(new_weights)
        if total_weight > 0:
            # Normalise all weights at once
            for p in new_particles:
                p.weight /= total_weight

        return self.resample(ParticleState(new_particles))


class ExpectedLikelihoodParticleFilter(ParticleFilter):

    def update(self, particle_state: ParticleState, measurements: np.ndarray) -> ParticleState:
        """
        Updates the weights of each particle based on the association probabilities of
        measurements.

        Parameters
        ----------
        particle_state : ParticleState
            The current state of the particles.
        measurements : np.ndarray
            Array of measurements to be associated with particles.

        Returns
        -------
        ParticleState
            The updated particle state after weighting based on expected likelihoods.
        """
        predicted_measurements = self.measurement_model.function(particle_state, noise=False)

        association_probabilities = np.zeros((len(measurements), predicted_measurements.shape[1]))

        # Calculate likelihoods of each particle for each measurement
        for i, measurement in enumerate(measurements):
            association_probabilities[i, :] = self.likelihood_function(
                measurement.state_vector, predicted_measurements, self.measurement_model.covar
            )

        # Update particle weights using PDA and normalise
        weights = np.array([particle.weight for particle in particle_state.particles])
        # Calculate expected likelihoods for all particles
        expected_likelihoods = np.mean(association_probabilities, axis=0)

        # Calculate new weights
        new_weights = weights * expected_likelihoods

        # Create new particles with updated weights
        new_particles = [
            Particle(particle.state_vector, new_weight)
            for particle, new_weight in zip(particle_state.particles, new_weights)
        ]

        # Normalise weights to sum to 1
        total_weight = np.sum(new_weights)
        if total_weight > 0:
            # Normalise all weights at once
            for p in new_particles:
                p.weight /= total_weight

        # Return resampled ParticleState if needed
        return self.resample(ParticleState(new_particles))
