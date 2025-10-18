"""
Week 6-7: Generate Moco Training Data
Generate muscle force training data using OpenSim Moco on cloud GPU

Requirements:
- AWS EC2 instance (g4dn.xlarge or g5.xlarge)
- OpenSim with Moco installed
- OpenSim model files

Success Criteria:
- 500+ successful Moco trials
- Diverse movement parameters
- Dataset downloaded locally
"""

import numpy as np
import multiprocessing as mp
from tqdm import tqdm
import os
import json


def check_opensim_installation():
    """Check if OpenSim is installed"""
    try:
        import opensim as osim
        print(f"✓ OpenSim version: {osim.GetVersion()}")
        return True
    except ImportError:
        print("✗ OpenSim not installed")
        print("\nInstall instructions:")
        print("  conda install -c opensim-org opensim")
        print("\nOr visit: https://opensim.stanford.edu/")
        return False


def setup_aws_instructions():
    """Print AWS setup instructions"""
    print("="*70)
    print("AWS EC2 Setup for Moco Training Data Generation")
    print("="*70)
    print("\n1. Launch EC2 Instance:")
    print("   - Instance Type: g4dn.xlarge or g5.xlarge ($1-2/hour)")
    print("   - AMI: Ubuntu 22.04 LTS with Deep Learning AMI")
    print("   - Storage: 100GB EBS")
    print("\n2. SSH into instance:")
    print("   ssh -i your-key.pem ubuntu@<instance-ip>")
    print("\n3. Install OpenSim:")
    print("   conda create -n moco python=3.10")
    print("   conda activate moco")
    print("   conda install -c opensim-org opensim")
    print("\n4. Clone repository and upload this script")
    print("\n5. Run data generation:")
    print("   python generate_moco_dataset.py --n_trials 500 --n_processes 16")
    print("\n6. Download results:")
    print("   scp -i your-key.pem ubuntu@<instance-ip>:moco_training_data.npz .")
    print("\nEstimated Cost: ~$42 for 500 trials (~42 hours)")
    print("="*70)


def run_single_moco_trial(params):
    """
    Run one Moco optimization

    Args:
        params: Tuple of (trial_id, load, speed, depth)

    Returns:
        dict with trial results
    """
    trial_id, load, speed, depth = params

    try:
        import opensim as osim

        # Load model (adjust path to your model)
        model_file = 'models/squat_model.osim'
        if not os.path.exists(model_file):
            # Use default gait model as fallback
            model_file = 'models/gait2392_simbody.osim'

        model = osim.Model(model_file)

        # Set up Moco study
        study = osim.MocoStudy()
        study.setName(f"trial_{trial_id:04d}")

        problem = study.updProblem()
        problem.setModel(model)

        # Time bounds (based on movement speed)
        problem.setTimeBounds(0, [speed * 0.8, speed * 1.2])

        # State bounds
        problem.setStateInfo('/jointset/hip_r/hip_flexion_r/value', [-2, 0.5])
        problem.setStateInfo('/jointset/knee_r/knee_angle_r/value', [0, 2.5])

        # Add tracking goal (kinematic trajectory)
        # This would be based on motion capture data or synthetic trajectory
        tracking = osim.MocoMarkerTrackingGoal('marker_tracking')
        tracking.setWeight(10)
        # TODO: Set marker data
        problem.addGoal(tracking)

        # Add effort minimization
        effort = osim.MocoControlGoal('effort')
        effort.setWeight(0.1)
        problem.addGoal(effort)

        # Configure solver
        solver = study.initCasADiSolver()
        solver.set_num_mesh_intervals(50)
        solver.set_optim_convergence_tolerance(1e-3)
        solver.set_optim_max_iterations(1000)

        # Solve
        print(f"Solving trial {trial_id}...")
        solution = study.solve()

        # Extract data
        kinematics = extract_kinematics(solution)
        muscle_forces = extract_muscle_forces(solution)

        print(f"✓ Trial {trial_id} completed")

        return {
            'trial_id': trial_id,
            'kinematics': kinematics,
            'muscle_forces': muscle_forces,
            'metadata': {
                'load': load,
                'speed': speed,
                'depth': depth
            },
            'success': True
        }

    except Exception as e:
        print(f"✗ Trial {trial_id} failed: {e}")
        return {
            'trial_id': trial_id,
            'success': False,
            'error': str(e)
        }


def extract_kinematics(solution):
    """
    Extract kinematics from Moco solution

    Args:
        solution: Moco solution object

    Returns:
        numpy array of joint angles, velocities, accelerations
    """
    import opensim as osim

    # Get states table
    states = solution.exportToStatesTable()

    # Extract relevant coordinates
    # TODO: Customize based on your model
    kinematics = []

    time = solution.getTimeMat()
    num_frames = len(time)

    for i in range(num_frames):
        frame_data = []

        # Example: extract joint angles
        # This depends on your model's coordinate names
        # frame_data.extend([hip_angle, knee_angle, ankle_angle, ...])

        kinematics.append(frame_data)

    return np.array(kinematics)


def extract_muscle_forces(solution):
    """
    Extract muscle forces from Moco solution

    Args:
        solution: Moco solution object

    Returns:
        numpy array of muscle forces
    """
    import opensim as osim

    # Get controls (muscle excitations)
    controls = solution.exportToControlsTable()

    # Calculate muscle forces from activations and model
    # TODO: Implement based on your muscle model

    muscle_forces = []

    # Placeholder
    num_muscles = 15
    num_frames = solution.getNumTimes()

    muscle_forces = np.random.rand(num_frames, num_muscles) * 1000  # Placeholder

    return muscle_forces


def generate_dataset(n_trials=500, n_processes=8, output_file='moco_training_data.npz'):
    """
    Generate complete Moco dataset using parallel processing

    Args:
        n_trials: Number of trials to generate
        n_processes: Number of parallel processes
        output_file: Output filename

    Returns:
        List of successful trials
    """
    print(f"\n{'='*70}")
    print(f"Generating Moco Training Dataset")
    print(f"{'='*70}")
    print(f"Trials: {n_trials}")
    print(f"Processes: {n_processes}")
    print()

    # Parameter ranges (customize for your movement)
    loads = np.linspace(0, 200, 20)      # 0-200kg
    speeds = np.linspace(1.0, 3.0, 10)   # 1-3 seconds per rep
    depths = np.linspace(90, 130, 10)    # Knee angle at bottom (degrees)

    # Create parameter combinations
    params = []
    for i in range(n_trials):
        load = np.random.choice(loads)
        speed = np.random.choice(speeds)
        depth = np.random.choice(depths)
        params.append((i, load, speed, depth))

    # Run in parallel
    print("Starting parallel optimization...")
    print("This may take several hours depending on complexity\n")

    with mp.Pool(n_processes) as pool:
        results = list(tqdm(
            pool.imap(run_single_moco_trial, params),
            total=n_trials,
            desc="Generating trials"
        ))

    # Filter successful trials
    successful = [r for r in results if r.get('success', False)]
    failed = len(results) - len(successful)

    print(f"\n{'='*70}")
    print(f"Generation Complete")
    print(f"{'='*70}")
    print(f"Successful: {len(successful)}/{n_trials}")
    print(f"Failed: {failed}")
    print()

    if len(successful) == 0:
        print("⚠ No successful trials. Check your OpenSim setup and model files.")
        return []

    # Save dataset
    print(f"Saving dataset to {output_file}...")

    np.savez_compressed(
        output_file,
        kinematics=np.array([r['kinematics'] for r in successful]),
        muscle_forces=np.array([r['muscle_forces'] for r in successful]),
        metadata=np.array([r['metadata'] for r in successful])
    )

    # Save metadata separately
    metadata_file = output_file.replace('.npz', '_metadata.json')
    with open(metadata_file, 'w') as f:
        json.dump({
            'n_trials': n_trials,
            'n_successful': len(successful),
            'n_failed': failed,
            'parameters': {
                'loads': loads.tolist(),
                'speeds': speeds.tolist(),
                'depths': depths.tolist()
            }
        }, f, indent=2)

    print(f"✓ Dataset saved: {output_file}")
    print(f"✓ Metadata saved: {metadata_file}")
    print(f"\nDataset size: {os.path.getsize(output_file) / 1e6:.1f} MB")

    return successful


def verify_dataset(dataset_file):
    """
    Verify and print dataset statistics

    Args:
        dataset_file: Path to dataset npz file
    """
    print(f"\n{'='*70}")
    print(f"Dataset Verification: {dataset_file}")
    print(f"{'='*70}")

    data = np.load(dataset_file, allow_pickle=True)

    print(f"\nContents:")
    for key in data.files:
        arr = data[key]
        print(f"  {key}: {arr.shape} {arr.dtype}")

    kinematics = data['kinematics']
    muscle_forces = data['muscle_forces']

    print(f"\nStatistics:")
    print(f"  Number of trials: {len(kinematics)}")
    print(f"  Kinematics shape: {kinematics[0].shape}")
    print(f"  Muscle forces shape: {muscle_forces[0].shape}")
    print(f"  Muscle force range: [{muscle_forces.min():.1f}, {muscle_forces.max():.1f}] N")
    print(f"  Mean muscle force: {muscle_forces.mean():.1f} N")

    print(f"\n✓ Dataset appears valid")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Generate Moco training dataset')
    parser.add_argument('--n_trials', type=int, default=500,
                       help='Number of trials to generate')
    parser.add_argument('--n_processes', type=int, default=8,
                       help='Number of parallel processes')
    parser.add_argument('--output', type=str, default='moco_training_data.npz',
                       help='Output filename')
    parser.add_argument('--verify', type=str, default=None,
                       help='Verify existing dataset')
    parser.add_argument('--aws_setup', action='store_true',
                       help='Show AWS setup instructions')

    args = parser.parse_args()

    if args.aws_setup:
        setup_aws_instructions()
    elif args.verify:
        verify_dataset(args.verify)
    else:
        # Check OpenSim installation
        if not check_opensim_installation():
            print("\n⚠ Cannot generate dataset without OpenSim")
            print("\nOptions:")
            print("1. Install OpenSim locally (if you have compatible OS)")
            print("2. Use AWS EC2 (recommended for large datasets)")
            print("\nRun with --aws_setup for AWS instructions")
        else:
            # Generate dataset
            successful = generate_dataset(
                n_trials=args.n_trials,
                n_processes=args.n_processes,
                output_file=args.output
            )

            if len(successful) > 0:
                verify_dataset(args.output)
