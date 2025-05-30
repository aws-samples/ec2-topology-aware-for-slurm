import boto3
import graphviz
import argparse
import logging
from collections import defaultdict
from datetime import datetime

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def get_cluster_instances(cluster_name, instance_type):
    """Get running compute instances from a specific cluster"""
    client = boto3.client('ec2')
    
    response = client.describe_instances(
        Filters=[
            {'Name': 'instance-type', 'Values': [instance_type]},
            {'Name': 'instance-state-name', 'Values': ['running']},
            {'Name': 'tag:parallelcluster:cluster-name', 'Values': [cluster_name]},
            {'Name': 'tag:parallelcluster:node-type', 'Values': ['Compute']}
        ]
    )

    instances = []
    for reservation in response['Reservations']:
        instances.extend(reservation['Instances'])

    logger.info(f'Found {len(instances)} instances in cluster {cluster_name}')
    return [instance['InstanceId'] for instance in instances]

def get_topology(instance_ids):
    """Get network topology for the specified instances"""
    client = boto3.client('ec2')
    topology = []
    
    # Process instance IDs in batches of 100
    for i in range(0, len(instance_ids), 100):
        batch = instance_ids[i:i+100]
        
        response = client.describe_instance_topology(InstanceIds=batch)
        topology.extend(response['Instances'])

        # Get additional pages if any
        while 'NextToken' in response:
            response = client.describe_instance_topology(
                InstanceIds=batch,
                NextToken=response['NextToken']
            )
            topology.extend(response['Instances'])

    logger.info(f'Retrieved topology for {len(topology)} instances')
    return topology
    
def create_visualization(topology, cluster_name, output_file='network_topology'):
    """Create a visual representation of the network topology"""
    dot = graphviz.Digraph(comment='Network Topology')
    dot.attr(rankdir='TB')  # Top to bottom layout

    # Add title with cluster name and date
    current_date = datetime.now().strftime('%m/%d/%Y')
    dot.attr(label=f'Cluster: {cluster_name}\nDate: {current_date}')
    dot.attr(labelloc='t')  # Place label at top
    dot.attr(fontsize='16')

    # Colors for different levels
    colors = {
        'level1': '#A7D2E8',  # Light Blue
        'level2': '#B8E6B3',  # Light Green
        'level3': '#F7E8AC',  # Light Yellow
        'instance': '#F5B7B1',  # Light Red/Pink
        'az_background': '#F0F3F4'  # Very Light Gray
    }

    # Group instances by AZ
    az_groups = defaultdict(list)
    for instance in topology:
        az_groups[instance['AvailabilityZone']].append(instance)

    # Create visualization for each AZ
    for az, instances in az_groups.items():
        with dot.subgraph(name=f'cluster_{az}') as az_cluster:
            az_cluster.attr(label=f'AZ: {az}', style='filled', fillcolor='#E8F6F3')
            
            # Group instances by their network path
            network_groups = defaultdict(list)
            for instance in instances:
                network_groups[tuple(instance['NetworkNodes'])].append(instance)

            # Create nodes and connections
            for network_path, instances_in_path in network_groups.items():
                # Create network level nodes
                for i, node_id in enumerate(network_path):
                    color = colors[f'level{i+1}']
                    label = f'Level {i+1}\n{node_id}'
                    dot.node(node_id, label, shape='box', style='filled', fillcolor=color)
                    
                    # Connect to previous level
                    if i > 0:
                        dot.edge(network_path[i-1], node_id)

                # Create instance nodes
                for instance in instances_in_path:
                    instance_id = instance['InstanceId']
                    label = f'{instance_id}\n{instance["InstanceType"]}'
                    dot.node(instance_id, label, shape='ellipse', 
                            style='filled', fillcolor=colors['instance'])
                    dot.edge(network_path[-1], instance_id)

    # Generate the visualization
    dot.render(output_file, format='png', cleanup=True)
    logger.info(f'Visualization saved as {output_file}.png')




def main():
    parser = argparse.ArgumentParser(description='Generate AWS EC2 network topology visualization')
    parser.add_argument('--cluster_name', required=True, help='ParallelCluster name')
    parser.add_argument('--instance_type', required=True, help='EC2 instance type')
    args = parser.parse_args()

    try:
        # Get instances from cluster
        instance_ids = get_cluster_instances(args.cluster_name, args.instance_type)
        if not instance_ids:
            logger.error("No instances found in cluster")
            return

        # Get topology information
        topology = get_topology(instance_ids)
        if not topology:
            logger.error("Could not retrieve topology information")
            return

        # Create visualization with cluster name in filename
        output_filename = f"{args.cluster_name}_topo"
        create_visualization(topology, args.cluster_name, output_filename)

    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
