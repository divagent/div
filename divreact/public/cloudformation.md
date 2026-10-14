aws sts get-caller-identity
aws configure list
aws configure get region

aws ecs list-clusters --region us-east-1
aws ecs list-services --cluster my-cluster --region us-east-1
aws ecs describe-services --cluster my-cluster --services backend-svc --region us-east-1

aws cloudformation validate-template --template-body file://path/to/iac/backend.yaml --region us-east-1

aws cloudformation create-change-set --stack-name backend-stack --change-set-name import-backend-01 --change-set-type IMPORT --resources-to-import file://path/to/iac/backend-import.json --template-body file://path/to/iac/backend.yaml --region us-east-1

aws cloudformation describe-change-set --stack-name backend-stack --change-set-name import-backend-01 --region us-east-1

aws cloudformation execute-change-set --stack-name backend-stack --change-set-name import-backend-01 --region us-east-1
aws cloudformation describe-stacks --stack-name backend-stack --region us-east-1 --query "Stacks[0].StackStatus"


aws cloudformation list-stack-resources --stack-name backend-stack --region us-east-1 --query "StackResourceSummaries[].{Logical:LogicalResourceId,Type:ResourceType,Status:ResourceStatus}"

aws ecs describe-services --cluster my-cluster --services backend-svc --region us-east-1 --query "services[0].{status:status,desired:desiredCount,running:runningCount,rollout:deployments[0].rolloutState}"

aws cloudformation detect-stack-drift --stack-name backend-stack --region us-east-1
aws cloudformation describe-stack-drift-detection-status --stack-drift-detection-id <drift-detection-id> --region us-east-1



aws ecs describe-services --cluster my-cluster --services frontend-svc --region us-east-1 --query "services[0].{taskDef:taskDefinition,desired:desiredCount,launch:launchType,platform:platformVersion,lb:loadBalancers,net:deployments[0].networkConfiguration,deployCfg:deploymentConfiguration}"

aws cloudformation validate-template --template-body file://path/to/iac/frontend.yaml --region us-east-1
aws cloudformation create-change-set --stack-name frontend-stack --change-set-name import-frontend-01 --change-set-type IMPORT --resources-to-import file://path/to/iac/frontend-import.json --template-body file://path/to/iac/frontend.yaml --region us-east-1

aws cloudformation describe-change-set --stack-name frontend-stack --change-set-name import-frontend-01 --region us-east-1
aws cloudformation execute-change-set --stack-name frontend-stack --change-set-name import-frontend-01 --region us-east-1
aws cloudformation describe-stacks --stack-name frontend-stack --region us-east-1 --query "Stacks[0].StackStatus"
aws cloudformation detect-stack-drift --stack-name frontend-stack --region us-east-1
aws cloudformation describe-stack-drift-detection-status --stack-drift-detection-id <drift-detection-id> --region us-east-1



Deploy:
aws cloudformation validate-template --template-body file://path/to/iac/frontend.yaml --region us-east-1
aws cloudformation create-change-set --stack-name frontend-stack --change-set-name add-taskdef-01 --change-set-type UPDATE --template-body file://path/to/iac/frontend.yaml --parameters ParameterKey=ImageTag,ParameterValue=frontend-v1 --region us-east-1
aws cloudformation describe-change-set --stack-name frontend-stack --change-set-name add-taskdef-01 --region us-east-1 --query "{status:Status,exec:ExecutionStatus,changes:Changes[].ResourceChange.{action:Action,logical:LogicalResourceId,type:ResourceType,replacement:Replacement}}"


aws cloudformation delete-change-set --stack-name frontend-stack --change-set-name add-taskdef-01 --region us-east-1
aws cloudformation validate-template --template-body file://path/to/iac/frontend.yaml --region us-east-1
aws cloudformation create-change-set --stack-name frontend-stack --change-set-name deploy-v2 --change-set-type UPDATE --template-body file://path/to/iac/frontend.yaml --parameters ParameterKey=ImageTag,ParameterValue=frontend-v2 --region us-east-1
aws cloudformation describe-change-set --stack-name frontend-stack --change-set-name deploy-v2 --region us-east-1 --query "{status:Status,exec:ExecutionStatus,changes:Changes[].ResourceChange.{action:Action,logical:LogicalResourceId,type:ResourceType,replacement:Replacement}}"
aws cloudformation execute-change-set --stack-name frontend-stack --change-set-name deploy-v2 --region us-east-1
aws cloudformation describe-stacks --stack-name frontend-stack --region us-east-1 --query "Stacks[0].StackStatus"


BFF:
aws ecs describe-task-definition --task-definition backend-svc:14 --region us-east-1 --query "taskDefinition.{family:family,cpu:cpu,memory:memory,networkMode:networkMode,requiresCompatibilities:requiresCompatibilities,runtimePlatform:runtimePlatform,executionRoleArn:executionRoleArn,taskRoleArn:taskRoleArn,volumes:volumes,ephemeralStorage:ephemeralStorage,containers:containerDefinitions}"

aws cloudformation validate-template --template-body file://path/to/iac/backend.yaml --region us-east-1

aws cloudformation create-change-set --stack-name backend-stack --change-set-name taskdef-baseline-01 --change-set-type UPDATE --template-body file://path/to/iac/backend.yaml --parameters ParameterKey=ImageTag,ParameterValue=backend-v1 --region us-east-1
aws cloudformation delete-change-set --stack-name backend-stack --change-set-name taskdef-baseline-01 --region us-east-1
aws cloudformation create-change-set --stack-name backend-stack --change-set-name deploy-v2 --change-set-type UPDATE --template-body file://path/to/iac/backend.yaml --parameters ParameterKey=ImageTag,ParameterValue=backend-v2 --region us-east-1
aws cloudformation describe-change-set --stack-name backend-stack --change-set-name deploy-v2 --region us-east-1 --query "{status:Status,exec:ExecutionStatus,changes:Changes[].ResourceChange.{action:Action,logical:LogicalResourceId,type:ResourceType,replacement:Replacement}}"


aws cloudformation execute-change-set --stack-name backend-stack --change-set-name deploy-v2 --region us-east-1
aws cloudformation describe-stacks --stack-name backend-stack --region us-east-1 --query "Stacks[0].StackStatus"

aws ecs describe-services --cluster my-cluster --services backend-svc --region us-east-1 --query "services[0].{taskDef:taskDefinition,running:runningCount,desired:desiredCount,rollout:deployments[0].rolloutState}"

curl -s http://<your-alb-host>/api/v1/health
