komidabot
=========

A Slack chat bot to request the daily menu at the [komida restaurants](https://www.uantwerpen.be/en/campus-life/catering/) of the [University of Antwerp](https://www.uantwerpen.be/en/).

![komidabot](komidabot.png)

About
-----

Komidabot retrieves the [menu for the komida restaurants](https://www.uantwerpen.be/nl/campusleven/eten/weekmenu/) at the University of Antwerp and lets you know what's for lunch on Slack.

Komidabot operates as a plugin for the official Slack [python-rtmbot](https://github.com/slackhq/python-rtmbot).

Komidabot will reply to menu requests on channels it has been invited to by (case insensitive):

* Mentioning 'komidabot' in your message, optionally specifying a campus and date.
* Matching the `^l+u+n+c+h+!+$` regex to retrieve the default menu of the present day at campus Middelheim.

Additionally, you can message komidabot directly without the need to use any of the above triggers.

* Campus choices can be specified using the full campus name or the three-letter campus abbreviation (Drie Eiken CDE, Middelheim / CMI, stad / city / CST).
* Dates can be specified using the day of the week (Monday - Sunday) or using temporal nouns (yesterday, today, tomorrow).

Installation
------------

Komidabot was developed using Python 3.6. No guarantees are given that it will work for other Python versions as well. See `requirements.txt` for the dependencies that need to be installed.

### How to add komidabot to your team's Slack?

1. Create a [custom bot user](https://api.slack.com/bot-users#custom_bot_users) for Slack.
2. Specify the API token as `SLACK_TOKEN` in the `rtmbot.conf` configuration file.
3. Run komidabot on your command line: `> rtmbot`.
4. Invite komidabot to any public channels on which you want to receive menu updates or message komidabot directly.
