# telegram_bot_service

A telegram bot you can extend that runs as a systemd service and run on your own services.

The base bot class implements:
* Loading the configuration from a file
* Starting up as a service
* Managing the message queues
* Registering the commands of the bot


At a minimum all you need to do is extend the class implement a method to respond to a message and the base class does the rest.


## Echo bot

### Creating a bot


### Running as a service

1. Copy the example serice file (`tg_bot.service`) to a new file `/etc/systemd/system/tg_bot.service`
2. Replace `user` with the username of your user
3. Change `ExecStart` to the path of your bot script
4. `sudo systemctl daemon-reload`
5. Start your bot `sudo systemctl start tg_bot`
6. `sudo systemctl enable tg_bot`
