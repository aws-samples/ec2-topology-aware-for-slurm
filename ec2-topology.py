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

    instance_ids = []
    for i in response['Reservations']:
        for j in i['Instances']:
            instance_ids.append(j['InstanceId'])

    return instance_ids


def get_instances_topology(ids):
    logger.info('Obtain topology of EC2 Instances: %s', ids)

    client = boto3.Session().client('ec2')

    response = client.describe_instance_topology(InstanceIds=ids)
    instances = []

    for i in response['Instances']:
        instances.append(i)

    while 'NextToken' in response:
        response = client.describe_instance_topology(
            InstanceIds=ids, NextToken=response['NextToken'])
        for i in response['Instances']:
            instances.append(i)

    return instances


def write_topo(switches, slurm_path):
    logger.info('Write topology file at %s/topology.conf', slurm_path)

    f = open(slurm_path + '/topology.conf', 'w+')
    for k, v in switches.items():
        f.write(f'SwitchName={k} Switches={",".join(list(v.keys()))}\n')
        for k2, v2 in v.items():
            f.write(f'SwitchName={k2} Switches={",".join(list(v2.keys()))}\n')
        for k3, v3 in v2.items():
            f.write(f'SwitchName={k3} Nodes={",".join(v3)}\n')
    f.close()


def get_instance_private_ip(ec2_instance):
    for n in ec2_instance.network_interfaces_attribute:
        if n['Attachment']['DeviceIndex'] == 0 and n['Attachment'][
                'NetworkCardIndex'] == 0:
            return n['PrivateIpAddress']


def get_slurm_node_name(ip_address):
    p = subprocess.run(['scontrol', 'show', 'nodes', '--json'],
                       capture_output=True)
    data = json.loads(p.stdout)

    for i in data['nodes']:
        if i['address'] == ip_address:
            node_name = i['name']
    return node_name


def get_slurm_hostname(instance_id):
    logger.info('Get EC2 Instance IDs and hotname association')

    ec2 = boto3.resource('ec2')
    instance = ec2.Instance(instance_id)
    private_ip = get_instance_private_ip(instance)
    hostname = get_slurm_node_name(private_ip)
    return hostname


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


def main():
    logger.setLevel(logging.INFO)
    logging.basicConfig(
        format=
        "%(asctime)s - [%(name)s:%(funcName)s] - %(levelname)s - %(message)s",
    )

    args = parse_args()
    instance_type = args.instance_type
    cluster_name = args.cluster_name

    instance_ids = get_instances(cluster_name, instance_type)

    if not instance_ids:
        logger.error('No running %s EC2 Instances found in the cluster %s',
                     instance_type, cluster_name)
        quit()

    instances = []
    for i in instance_ids:
        instances += get_instances_topology([i])

    switches = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for i in instances:
        if 'NetworkNodes' in i:
            top_level = i['NetworkNodes'][0]
            mid_level = i['NetworkNodes'][1]
            low_level = i['NetworkNodes'][2]

            switches[top_level][mid_level][low_level].append(
                get_slurm_hostname(i['InstanceId']))

    switches = json.loads(json.dumps(switches))
    write_topo(switches, args.slurm_path)

    logger.info('End')


if __name__ == '__main__':
    main()
