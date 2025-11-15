# Route Optimizer

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Description

Holidays are special moments that provide an opportunity to unwind and create lasting memories. We often come across situations where we want to visit numerous attractions but have limited time.
Efficient trip planning enhances the holiday experience by saving time and costs. Also, it is sustainable to efficiently plan trip to utilize reduce carbon emissions.

This solution discussed in next sections provides an alternative to plan trip that utilizes principles of [Travelling Salesman Problem](https://en.wikipedia.org/wiki/Travelling_salesman_problem) to determine the route that covers all attractions. It utilizes the Google Maps service to determine distances between attractions and uses TSP to determine the optimal itenerary.
Additionally, features such as Lunch and dinner hours and durations can also be specified to determine the tour schedule.

## Table of Contents

- [PreRequisite](#prerequisite)
- [Installation](#installation)
- [Usage](#usage)
- [License](#license)
- [Contact](#contact)

## PreRequisite

### Technology Stack

### AWS Cloud Platform

The solution utilizes AWS Cloud platform services to provision resources. Ensure that you have AWS Cloud neccessary access to Console and CLI to deploy and use the solution.

### Google Cloud APIs

Google provides one of the best in map service. These can be utlized using API calls via Google Cloud APIs. Follow [Google Cloud API Reference](https://cloud.google.com/docs/authentication/api-keys) for steps to configure API.

### Terraform

Route Optimizwer solution's AWS resources are provisioned using Terraform. You must ensure latest version of Terraform is installed on PC.

## Installation

### Install and configuration AWS CLI

Follow [AWS CLI Installation Steps](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) to install AWS CLI. Configure the AWS CLI environment to connect to the AWS Cloud Console by following the [CLI configuration Steps](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html).

```bash
/mnt/d/Project/routeoptimizer (main)
└─ $ ▶ aws configure
AWS Access Key ID [None]: <Access Key ID>
AWS Secret Access Key [None]: <Secret Access Key>
Default region name [None]: us-east-1
Default output format [None]: json
/mnt/d/Project/routeoptimizer (main)
└─ $ ▶ 
```

### Clone Repository

Clone Route Optimizer repository from GitHub repository.

```bash
git clone https://github.com/animesh303/routeoptimizer.git
```

### Create and modify variables

Create and update variables in parameters files.

```bash
cp -rp secrets.tfvars.template secrets.tfvars
cp -rp config.tfvars.template config.tfvars
```

Below are variables that should be updated.

```tfvars
# secrets.tfvars
# Refer to https://cloud.google.com/docs/authentication/api-keys for more information
google_api_key = "<insert_api_key>"
```

```tfvars
# Durations of lunch and dinner
lunch_duration_mins  = 60
dinner_duration_mins = 60

# Hour in the day when the lunch or dinner should start
lunch_hr             = 12
dinner_hr            = 19
```

### Deploy Terraform code

```bash
terraform init
terraform plan -var-file=secrets.tfvars -var-file=config.tfvars
terraform apply -var-file=secrets.tfvars -var-file=config.tfvars --auto-approve
```

> Please note the output value for ***assignment_bucket*** that will be used later

### Usage

#### Modify the attractions.xlsx

Modify the data/attractions.xlsx file. This has 2 columns, ***Attractions*** and ***Leisure Time (Mins)***. Fill the column with list of places as you find in Google Maps.
> ***Note:*** Some places may need to have address properly mentioned for this solution to work.

The first location will be the origin position. The route will be starting and terminated at this location.

#### Upload the attractions.xlsx

```bash
aws s3 cp data/attractions.xlsx s3://<assignment_bucket>
```

#### Trigger Lambda Function

```bash
aws lambda invoke --function-name RouteOptimizer response.json
```

### Download and verify optimized routes

```bash
aws s3 sync s3://routeoptimizerakn data/
```

### License

This project is licensed under the MIT License.

### Contact

Name: Animesh Kumar Naskar
Email: <animesh303@gmail.com>
