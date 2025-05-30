#!/usr/bin/env python3

import argparse
import boto3
import logging
import json
import subprocess

from collections import defaultdict

logger = logging.getLogger(__name__)


def get_instances(cluster_name, instance_type):
    logger.info('List %s EC2 Instances belonging to %s', instance_type,
                cluster_name)

    client = boto3.Session().client('ec2')

    try:
        response = client.describe_instances(
            Filters=[{
                'Name': 'instance-type',
                'Values': [
                    instance_type,
                ]
            }, {
                'Name': 'instance-state-name',
                'Values': [
                    'running',
                ]
            }, {
                'Name': 'tag:parallelcluster:cluster-name',
                'Values': [
                    cluster_name,
                ]
            }, {
                'Name': 'tag:parallelcluster:node-type',
                'Values': [
                    'Compute',
                ]
            }])

    except botocore.exceptions.ClientError as e:
        logger.error('An error occurred: %s', e)

    instances = []
    for i in response['Reservations']:
        for j in i['Instances']:
            instances.append(j)

    return instances


def get_instances_topology(ids):
    logger.info('Obtain topology of EC2 Instances: %s', ids)

    client = boto3.Session().client('ec2')

    response = client.describe_instance_topology(InstanceIds=ids)

    instances = []
    instances = response['Instances'].copy()

    while 'NextToken' in response:
        response = client.describe_instance_topology(
            InstanceIds=ids, NextToken=response['NextToken'])
        for i in response['Instances']:
            instances.append(i)

    return instances


def recurse_topo(file, topology):
    for k, v in topology.items():
        if isinstance(v, dict):
            file.write(f'SwitchName={k} Switches={",".join(list(v.keys()))}\n')
            recurse_topo(file, v)
        else:
            file.write(f'SwitchName={k} Nodes={",".join(v)}\n')


def write_topo(switches, slurm_path):
    logger.info('Write topology file at %s/topology.conf', slurm_path)

    f = open(slurm_path + '/topology.conf', 'w+')
    recurse_topo(f, switches)
    f.close()


def get_instance_primary_private_ip(ec2_instance):
    for n in ec2_instance['NetworkInterfaces']:
        if n['Attachment']['DeviceIndex'] == 0 and n['Attachment'][
                'NetworkCardIndex'] == 0:
            return n['PrivateIpAddress']


def get_slurm_node_info():
    p = subprocess.run(['scontrol', 'show', 'nodes', '--json'],
                       capture_output=True)
    return json.loads(p.stdout)


SLURM_NODES = get_slurm_node_info()


def get_slurm_node_name(ip_address):

    for i in SLURM_NODES['nodes']:
        if i['address'] == ip_address:
            node_name = i['name']
    return node_name


def instances_slurm_hostnames_mapping(instances):
    logger.info('Get EC2 Instance IDs and hotnames association')

    ids_hostnames_map = {}
    for i in instances:
        private_ip = get_instance_primary_private_ip(i)
        ids_hostnames_map[i['InstanceId']] = get_slurm_node_name(private_ip)
    return ids_hostnames_map


def parse_args():
    parser = argparse.ArgumentParser(
        description='Generate a topology configuration file for slurm')

    parser.add_argument('--cluster_name',
                        type=str,
                        required=True,
                        help='Slurm cluster name on AWS')

    parser.add_argument('--instance_type',
                        type=str,
                        help='Amazon EC2 Instance Type')

    parser.add_argument('--slurm_path',
                        type=str,
                        default='/opt/slurm/etc',
                        help='Path to slurm etc')

    return parser.parse_args()


def chunk(l, size):
    return [l[pos:pos + size] for pos in range(0, len(l), size)]


def create_nested_dict():
    return defaultdict(create_nested_dict)


def add_instance_nested(dic, val, network, max_level, cur_level=0):

    if cur_level < max_level:
        dic[network[cur_level]] = add_instance_nested(dic[network[cur_level]],
                                                      val, network, max_level,
                                                      cur_level + 1)

        return dic
    else:
        if len(dic) == 0:
            return [val]
        else:
            return dic + [val]


def main():
    logger.setLevel(logging.INFO)
    logging.basicConfig(
        format=
        "%(asctime)s - [%(name)s:%(funcName)s] - %(levelname)s - %(message)s",
    )

    args = parse_args()
    instance_type = args.instance_type
    cluster_name = args.cluster_name

    instances = get_instances(cluster_name, instance_type)

    if not instances:
        logger.error('No running %s EC2 Instances found in the cluster %s',
                     instance_type, cluster_name)
        quit()

    instances_topology = []
    for i in chunk(instances, 100):
        ids = [k['InstanceId'] for k in i]
        instances_topology += get_instances_topology(ids)

    instances_slurm_hostnames = instances_slurm_hostnames_mapping(instances)

    switches = create_nested_dict()
    for i in instances_topology:
        network = i.get('NetworkNodes')
        if network is not None:
            nb_network_level = len(network)

            add_instance_nested(switches,
                                instances_slurm_hostnames[i['InstanceId']],
                                network, nb_network_level)

    switches = json.loads(json.dumps(switches))
    write_topo(switches, args.slurm_path)

    logger.info('End')


if __name__ == '__main__':
    main()