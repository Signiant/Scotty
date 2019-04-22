**Scotty**

The aim of this little project is to create a slack bot and an AWS Lex Bot that communicate to each 
other via simple commands to acheive complex tasks such as creating policies to allow access specific
DynamoDB tables for IAM groups. The bot validates if the user has permission to access the table they
have requested as well as if the user is a member of the workspace.

**Let Get Started: First Time Deploy**

    - Create Slack WebHook
        - In top left hand corner of your workspace, there is an drop down bar
        - Go to Manage App under Adminstration, which will lead to a web page
        - On the left hand side of the web page there a side menu. click on custom integrations
          then choose incoming webhook
        - click add configuration right under the left hand image
        - then choose a channel to post to
        - save the Webhook URL
        
    - Create Slack App
        - go to https://api.slack.com and top right hand corner of the website click Your Apps
        - then click Create New App
            - Fill in App Name and choose the Development Slack Workspace (if applicable)
                - click Create App
                - under Basic Information (left menu), save the following (under App Credentials)
                    - Client ID
                    - Client Secret
                    - Verification Token
                - under Bot Users (left menu), click 'Add a Bot User'
                    - Provide a Display name and Default username
                    - Enable 'Always Show My Bot as Online'
                    - To save the changes, choose Add Bot User
                - under OAuth & Permissions (left menu)
                    - click 'Install App to Workspace'
                    - save the OAuth Access Token

    - Deploy the LEX Bot
        - export AWS_PROFILE=<profile> (or equivalent AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)
        - if required, create the S3 bucket that will be used during the deployment of the lambda function(s)
        - run deploy.sh script
            - requires 8 arguments to be passed in:
                - name of the s3 bucket to use during deployment of lambda(s)
                - name of the AWS LEX BOT to create/update
                - The region where the Lex bot will be deployed in
                - WebHook that you created in creating a webhook
                - OAuth Access Token that you received from slack Application
                - Notification Channel(s) that Scotty will post to
                - AWS IAM Groups that are allowed to use Scotty
                - User List of Admins that can perform restricted actions

    Ex) sh deploy.sh <Bucket_Name> <Bot_Name> <Region> <Webhook> <OAuth Access Token> <Slack Notification Channels> <Allowed Groups> <Admin User List>

    Once the AWS bot is deployed in the region of your choosing. A couple of the elements need to be manually set up.

        Visit the AWS Lex console and select the Scotty bot that was just deployed
            - for each of the intents, select the intent and allow permission for the lambda function associated with the intent (pop-up window)
            - perform the channel integrations for Slack (Channels tab)
                - Channel name
                - KMS key=aws/lex
                - Alias (select Prod from dropdown)
                - Client Id from slack Basic Information
                - Client Secret from slack Basic Information
                - Verification Token from slack Basic Information
            - click 'Activate'
                - save the call back URLs displayed
    
        Configuring the Slack application:
            - In the left menu, choose Interactive Components
                - Enable 'Interactivity'
                - In the Request URL box, add the Postback URL acquired from the AWS channel tab
                - Click Save Changes (bottom right)

            - Event Subcriptions (left menu)
                - Enable 'Enable events'
                - In the Request URL box, add the Postback URL acquired from the AWS channel tab
                - Add the following bot events under the Subscribe to Bot Events (click 'Add Bot User Event'):
                    - app_mention
                    - message.channels
                    - message.groups
                    - message.im
                - Click Save Changes (bottom right)
    
            - OAuth & permission(left menu)
                - click the 'Add New Redirect URL' button
                    - In the Redirect URLs box, add the OAuth URL acquired from the AWS channel tab
                        - click 'Add'
                        - click 'Save URLs'
                -Add the following permission under Scopes
                    - Conversations
                        - Send messages as <Display Name> (chat:write:bot)
                        - Post to specific channels in Slack (incoming-webhook)
                    - Users
                        - Access your workspace's profile information (users:read)
                        - View email addresses of people on this workspace (users:read.email)
                    - Workspace Info
                        - Access information about your workspace (team:read)

                    - Interactivity (this like already exists due to actions above)
                        - Add a bot user with the username <bot username> (bot)

                - Click Save Changes
                    - you will likely need to re-authorize the app (message at the top of the screen)
                    - alternatively choose Manage Distribution (left menu) and choose Add to Slack to install the application

            - Manage Distribution (left menu)
                - Choose 'Add to Slack' to install the application
                - Authorize the bot to respond to messages


**Subsequent Deploys**

    Simply run the deploy.sh script

    Ex: sh deploy.sh <Bucket_Name> <Bot_Name> <Region> <Webhook> <OAuth Access Token> <Slack Notification Channels> <Allowed Groups> <Admin User List>


**Adding New Intents:**

    - create new json file in LexBot/intents named after intent (eg. Scotty_IntentName) that describes the intent
    - update the LexBot/slots.json file with any new slots that are needed
    - if there is a lambda function needed for the intent, create a new folder under LambdaSource named after the intent
        - should contain:
            - template.yaml: Cloudformation template file
            - lambdaHandler.py: source code for the lambda function
            - requirements.txt (if extra python modules are required)
    - deploy.sh script will need to be updated to deply the new lambda function
