#!/bin/bash

Deploy_ScottyResources()
{
    local STACKNAME=$1

    echo "Attempting to Create/Update $STACKNAME"

    STACKSTATUS=$(aws cloudformation describe-stacks --stack-name $STACKNAME --region $Region --output text --query 'Stacks[0].StackStatus' 2> /dev/null)
    STATUS=$?
    COMMAND="create-stack"
    if [ $STATUS -eq 0 ]; then
        COMMAND="update-stack"
        echo "   Checking if update-stack can be performed on stack $STACKNAME ..."
        echo $STACKSTATUS | grep -q "COMPLETE"
        if [ $? -eq 1 ]; then
            echo "   *** ERROR ***"
            echo "   *** Stack is NOT in an updatable state"
            echo "   *** Current stack status is $STACKSTATUS"
            exit 1
        fi
        echo $STACKSTATUS | grep -q "PROGRESS"
        if [ $? -eq 0 ]; then
            echo "   *** ERROR ***"
            echo "   *** Stack is NOT in an updatable state"
            echo "   *** Current stack status is $STACKSTATUS"
            exit 1
        fi
    fi

    echo "   Performing $COMMAND on stack $STACKNAME"

    STACKID=$(aws cloudformation $COMMAND --stack-name $STACKNAME --region $Region --template-body "file://LexBot/cfn-template.yaml" --output text 2>&1)
    STACK_COMMAND_RETCODE=$?

    if [ $STACK_COMMAND_RETCODE -ne 0 ]; then
        echo $STACKID | grep -q "ValidationError"
        STATUS=$?
        if [ $STATUS -eq 0 ]; then
            # we had a validation error - was it simply a case that the stack was the same and had no changes?
            echo $STACKID | grep -q "No updates"
            if [ $? -eq 1 ]; then
                # it WAS a validation error but not a simple 'no updates' message
                echo "   *** ERROR - Command failed with code $STATUS ($STACKID)"
                exit 1
            else
                echo "   Stack has no changes - no updates performed, continuing..."
            fi
        else
            echo "   *** ERROR - Command $COMMAND failed with code $STACK_COMMAND_RETCODE"
            exit 1
        fi
    fi
}

Deploy_Lambda()
{
    local PATH_TO_SOURCE=$1
    local FunctionName=$2
    local ParameterOverrides=$3

    local PARAM_OVR=""
    if [ "$ParameterOverrides" != "" ]; then
        PARAM_OVR="--parameter-overrides ${ParameterOverrides}"
    fi

    # Replace underscores with dashes for the stack name
    local StackName=$(echo ${FunctionName//_/-})

    echo ""
    LambdaFunctionName=Scotty-TableAccess
    echo "Switching to $PATH_TO_SOURCE folder"
    pushd $PATH_TO_SOURCE > /dev/null
    echo "Packaging up ${FunctionName} lambda for deployment..."
    rm -rf build
    mkdir -p build
    cp lambdaHandler.py build/
    if [ -e requirements.txt ]; then
        pip install -r requirements.txt --target build > /dev/null 2>&1
    fi
    aws cloudformation package --template-file template.yaml --s3-bucket $BucketName --s3-prefix ${FunctionName} --output-template-file packaged-template.yaml --region $Region > /dev/null
    RETCODE=$?
    if [ $RETCODE -ne 0 ]; then
        echo "Failed to create package"
        exit $RETCODE
    fi
    echo "Deploying ${FunctionName} lambda..."
    aws cloudformation deploy --template-file packaged-template.yaml --stack-name ${StackName} ${PARAM_OVR} --capabilities CAPABILITY_IAM --region $Region
    RETCODE=$?
    if [ $RETCODE -ne 0 ]; then
        echo "Package failed to deploy"
        exit $RETCODE
    fi
    popd > /dev/null
}

if [ $# -eq 8 ]; then

    BucketName=$1
    BotName=$2
    Region=$3
    hookUrl=$4
    api_token=$5
    notificationChannel=$6
    groups=$7
    userList=$8

    echo "Lambda Deploy Bucket Name provided: $BucketName"

    # This is a deployment script for Scotty
    RETCODE=0

    dynamoDBTable=Scotty_Config

    # Deploy the ScottyResources Stack
    STACKNAME=Scotty-Resources
    Deploy_ScottyResources $STACKNAME

#    # TODO: Would be nice to find a way to deploy the lambdas via a loop through the LambdaSource folder, eg.
#    for dir in LambdaSource/*/
#    do
#        dir=${dir%*/}      # remove the trailing "/"
#        FunctionName=$(${dir##*/})
#        Deploy_Lambda LambdaSource/${FunctionName} ${FunctionName} "${INPUT_PARAMETERS}"
#    done

    # Deploy Help Lambda
    Deploy_Lambda LambdaSource/Scotty_Help Scotty_Help "apiToken=$api_token userList=$userList"

    # Deploy Table Access Lambda
    Deploy_Lambda LambdaSource/Scotty_TableAccess Scotty_TableAccess "HookUrl=$hookUrl apiToken=$api_token Channel=$notificationChannel groups=$groups dynamoDBTable=$dynamoDBTable"

    # Deploy Blacklist Lambda
    Deploy_Lambda LambdaSource/Scotty_Blacklist Scotty_Blacklist "apiToken=$api_token userList=$userList dynamoDBTable=$dynamoDBTable"

    echo ""
    # Deploy LexBot
    pushd LexBot > /dev/null
        python Lexbot-deploy.py --name $BotName  --region $Region
    popd > /dev/null

    # Deploy Table Slot Updater Lambda
    Deploy_Lambda LambdaSource/Scotty_TableSlotUpdater Scotty_TableSlotUpdater

    # Run the tableSlotUpdater lambda
    echo ""
    echo "Running the Scotty-TableSlotUpdater lambda"
    pushd LambdaSource/Scotty_TableSlotUpdater > /dev/null
        aws lambda invoke --function-name Scotty_TableSlotUpdater outfile.txt --region $Region
    popd > /dev/null

else
   echo "Must provide 8 arguments: BucketName, BotName, Region, WebHook, Slack OAuth Access Token, Slack Notification channel, Allowed Groups, Blacklist User List"
   RETCODE=1
fi

exit $RETCODE
