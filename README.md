# Requirements

To get started with this application, you'll need to install the necessary Python packages. Run the following command in your terminal:

```
pip install python-dotenv slack-bolt slack-sdk
```

# Creating a Slack Application in Socket Mode

To enable Slack integration, you need to create a Slack application in Socket Mode. Follow these steps:

1. Go to the [Slack API](https://api.slack.com/apps) and click "Create New App."
2. Choose "From scratch" and provide a name for your app (e.g., `AttendanceApp`). Select your Slack workspace.
3. Under "Settings," navigate to "Socket Mode" and enable it.
4. Create and save a new App-Level Token with the required permissions (e.g., `connections:write`).
5. Under "OAuth & Permissions," add the following bot scopes:
	- `channels:read`
	- `chat:write`
	- `commands`
	- `users:read`
	- `usergroups:read`
	- `files:write`
1. Install the app to your workspace and retrieve the Bot User OAuth Token.
2. Save the App-Level Token and Bot User OAuth Token in a `.env` file for your application:
    
    ```env
    SLACK_APP_TOKEN=xapp-1-...
    SLACK_BOT_TOKEN=xoxb-...
    ```
    

Your Slack app is now set up and ready to communicate in Socket Mode.

# Creating a Slack User Group for Administrators

To manage the application's administrative tasks, create a user group on Slack for administrators. Follow these steps:

1. Open your Slack workspace.
2. Go to "People" and select "User Groups."
3. Click on "Create Group" and name it appropriately (e.g., `Administrators`).
4. Add the relevant team members to the group.
5. Save the group.

This group will be used for managing the application.

# Setting up the Database

To set up the database, follow these steps:

1. Ensure you have MySQL or MariaDB installed on your system.
    
2. Create a new database named `attendance` by running the following command in your database client:
    
    ```sql
    CREATE DATABASE attendance;
    ```
    
3. Create a new user and grant the necessary privileges:
    
    ```sql
    CREATE USER 'attendance_user'@'localhost' IDENTIFIED BY 'secure_password';
    GRANT ALL PRIVILEGES ON attendance.* TO 'attendance_user'@'localhost';
    FLUSH PRIVILEGES;
    ```
    
    Replace `attendance_user` with your desired username and `secure_password` with a strong password.
    
4. Import the database schema from the provided `db.sql` file. Run this command:
    
    ```bash
    mysql -u [username] -p attendance < path/to/db.sql
    ```
    
    Replace `[username]` with your database username and `path/to/db.sql` with the path to the `db.sql` file.
    

Your database is now ready to be used with the application.

# Running `usergroups.py` to Retrieve Group ID

Before proceeding, run the `usergroups.py` script to retrieve the ID of the Slack user group you created for administrators. This ID will be used to configure the application.

# Setting up `config.ini`

After retrieving the administrator group ID, create and configure the `config.ini` file. Below is an example configuration:

```
[settings]
# Mandatory
admin_group=GROUP_ID
# Optional
active_men_players=
active_women_players=
export_channel=
coming_text=Chci
late_text=Ještě nevím
notcoming_text=Nechci
coming_training=Přijdu
late_training=Přijdu později
notcoming_training=Nepřijdu

#Mandatory
[database]
host=localhost
user=USER
password=PASSWORD
database=DATABASE
```

Replace the placeholders with the actual values for your setup. The `admin_group` field is mandatory and must contain the ID retrieved from `usergroups.py`.

Your config file is now ready to be used with the application.
