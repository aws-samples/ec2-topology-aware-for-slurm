# Amazon EC2 Topology Aware for Slurm

This project allows AWS ParallelCluster with the Slurm scheduler to be aware of the Amazon EC2 Instances network topology.
It enables jobs to be placed on nodes in close network proximity with [Slurm topology plugin](https://slurm.schedmd.com/topology.html).

In November 2023, AWS announced the [Instance Topology API](https://aws.amazon.com/about-aws/whats-new/2023/11/instance-topology-api-ml-hpc-workloads/).
It provides customers a unique per account hierarchical view of the relative proximity between Amazon EC2 instances.
To learn more, please visit the [EC2 User Guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-topology.html).

This solution walks you through the steps to:
- Create a topology configuration for Slurm based the EC2 Instance topology information.
- Enable the topology plugin in Slurm.
- Update Slurm configuration to use topology-aware scheduling.

**NOTE**:We recommend this solution for static compute cluster.

## Prerequisites

Before starting, make sure you have the following permission on the AWS ParallelCluster HeadNode:

```bash
ec2:DescribeInstanceTopology
```

You can add this by adding the `arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess` managed policy to the HeadNode [AdditionalIamPolicies](https://docs.aws.amazon.com/parallelcluster/latest/ug/HeadNode-v3.html#yaml-HeadNode-Iam-AdditionalIamPolicies) config.

## Create the topology configuration
You start creating the `topology.conf` file that describes the network topology of the Amazon EC2 Instances of your cluster.

Connect to the **HeadNode** of your AWS ParallelCluser based and download the content of this repository:
```bash
git clone https://github.com/aws-samples/ec2-topology-aware-for-slurm.git
cd ec2-topology-aware-for-slurm
```

The `ec2-topology.py` script takes as argument the cluster **NAME** and **the Amazon EC2 instance type** associated with the Slurm partition.
For this step and the following, you will need to become `root` user create the `topology.conf` configuration file and restart slurm services.
```bash
sudo -s
```

Let's create a Python Virtual Environment.
```bash
export AWS_DEFAULT_REGION=$(TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"` \
&& curl -H "X-aws-ec2-metadata-token: $TOKEN" -v http://169.254.169.254/latest/meta-data/placement/region)

python3 -m venv env
source env/bin/activate

python3 -m pip install --upgrade pip
pip3 install -r requirements.txt
```

Run the `ec2-topology.py` Python script that will create the `topology.conf` file at `/opt/slurm/etc/`.
```bash
python3 ec2-topology.py --cluster_name [CLUSTER_NAME] --instance_type [INSTANCE_TYPE]
```

Exit the Python Virtual Environment.

```bash
deactivate
```

## Enable topology configuration to slurm

Edit the Slurm configuration file, `slurm.conf`, to setup topology-aware scheduling.

```bash
cat >> /opt/slurm/etc/slurm.conf << EOF
TopologyPlugin=topology/tree
TopologyParam=RouteTree
EOF
```

## Update Slurm configuration

After editing, you will ask the compute node to re-read the `slurm.conf` file and restart the slurm controller.

```bash
scontrol reconfigure
systemctl restart slurmctld
```

Your Slurm jobs will now be scheduled based on the Amazon EC2 instance topology.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

