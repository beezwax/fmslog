# fmslog
## Display FileMaker Server logs & resource usage

Some things that it does that using just tail, head, or Get-Content don't:
- improved formatting, including consistent column alignments with headers
- quickly display or open logs in editor (don't have to type full log path)
- limit messages to those only after a given timestamp or duration
- lists path, size, and modification dates for all logs
- optionally truncate lines to avoid line wrap
- FMS processes and network ports in use
- sizes of database directories
- connectivity tests for 10 different FMS endpoints
- list versions of FMS components (NodeJS, Tomcat, etc.)

Design Goals:
- very simple installation
- support all three server environments: macOS, Ubuntu, and Windows
- consolidates access to various logs
- no waiting for logs to import

---

## REFERENCES & RELATED

* FMS Help - Event log: https://help.claris.com/en/server-help/content/monitor-event-log.html
* FMS Help - Monitoring FileMaker Server: https://help.claris.com/en/server-help/content/monitor-server.html
* General Web Publishing Settings for Server: https://support.claris.com/s/answerview?anum=000023506
* Log Viewer for Claris FileMaker: https://luminfire.com/our-solutions/claris-filemaker-log-viewer/
* Ports used by FileMaker Server: https://help.claris.com/en/server-installation-configuration-guide/content/ports-used-by-server.html
* Top Call statistics logging: https://support.claris.com/s/answerview?anum=000025776
* Tracking activity in log files in FileMaker Server: https://support.claris.com/s/article/Tracking-activity-in-log-files-in-FileMaker-Server-1503692942153
* FileMakerPortScanner: https://github.com/DimitrisKok/FileMakerPortScanner
* How to Troubleshoot WebDirect Downtime in Your FileMaker Application: https://www.soliantconsulting.com/blog/troubleshoot-filemaker-webdirect-downtime/

---

## CURRENT ISSUES

Current functionality with major issues:
- `-b` or `--begin`: only working with durations (eg, 'd' or '1d' for 1 day)
- `-B` or `--backups`: may list backup sets twice if target dir is used more than once but using different path
- `-C` or `--check-connectivity`: VPN connection may confuse tests
- `-m` or `--merge`: not implemented
- `-s` or `--succinct`: partially implemented
- `--ssh`: not implemented
- `-t` or `--tail`: may not print current log segment before starting to follow/tail
- nginx/apache/IIS: log parsing not fully implemented

---

## INSTALLATION & REQUIREMENTS

Copy the latest version of the `fmslog` file to a directory in user's command PATH:

* macOS: `sudo curl -o /usr/local/bin/fmslog https://raw.githubusercontent.com/beezwax/fmslog/refs/heads/main/fmslog && sudo chmod +x /usr/local/bin/fmslog`
* Ubuntu: `sudo curl -o /usr/bin/fmslog https://raw.githubusercontent.com/beezwax/fmslog/refs/heads/main/fmslog && sudo chmod +x /usr/bin/fmslog`

Requires Python 3.9 or newer.

---

## OPTIONS & PARAMETERS

```
usage: fmslog [-b BEGIN] [-e EDIT] [-f FILTER] [-h] [-H] [-i] [-l] [-L] [-m] [-n NUMBER] [-p PASSWORD] [-S SET] [-s] [--ssh SSH] [-t] [--tail TAIL] [--truncate] [-u USER] [-N] [-v] [logs ...]
              [logname]
               
View FileMaker Server logs and set logging options

positional arguments (log name):
  {access,admin,clientstats,dapi,event,fac,fmodatadebug,fmsadmindebug,fmsasedebug,fmscwpc,fmscwpcli,fmsdebug,fmsgetpasskeyebug,fmshdebug,fmshelper,fmslogdebug,fmwipd,httpaccess,httpdctlerr,httpdctlout,httperror,httpsslaccess,httpsslerror,install,httpaccess,loadschedules,odata,scriptevent,stats,stderr,stdout,topcall,trimlog,wpe,wpedebug,interval,clientstats,fmsdebug,logsize,topcall}

options:
  -B, --backups             list scheduled backup sets present, including total number of files and size
  -b, --begin BEGIN         start at first message on or after time or time interval in BEGIN
  -C, --check-connectivity	test connectivity to FMS components
  -D, --data                list directories being used for databases, external container data, documents, and temp files
  -e, --edit                open the log in a text editor; first try $EDITOR, then GUI editor (macOS), then nano
  -f, --filter FILTER       only return lines matching regex expression FILTER
  --dir LOG                 print the directory path of the named log
  -h, --head                display the start of the specified log files instead of its tail
  --help                    display command details
  -H, --headers-off         turn off headers for all logs
  --host-info               extended list server configuration settings; requires admin console credentials (-u and -p)
  -i, --ignore-case         make filter's regex case insensitive
  -L, --list                list all log files and crash reports, including size, date created & modified, sorted by modification time
  -n, --number RANGE        quantity of lines to print
  -N, --network             network usage info
  -P, --process-info        metrics for FMS processes
  -S, --set SET             change log configuration options
  --start-fms               start the FileMaker Server service
  --stop-fms                stop the FileMaker Server service
  -s, --succinct            strip less useful details from log output (partially implemented)
  -t, --tail                wait for any new messages after printing current end of log
  --truncate                cut off any output if beyond width of screen
  -V, --version             version info for fmslog and FMS components
```

---

### -b, --begin
Start printing logs on or after the given duration. Durations are an optional number followed by:
- 's': seconds from now
- 'm': minutes from now
- 'h': hours from now
- 'd': days since midnight today (e.g., '2d' would be from midnight yesterday)

### -B, --backups

List the paths, their sizes, and total size of hard linked files in backup sets. Target paths are determined by scanning FMS' preferences file.

Typical disk usage calculations may overstate actual usage, since backup sets can use shared (hard linked) copies of the same data
if there were no changes between the backup sets and the backups were created with the same backup schedule. By subtracting the size of the hard
linked files from the total size you can get the total size of unique files in each backup.

On macOS, it is possible to have multiple target folders that FMS' will still resolve to the same location. Typically this is because
the boot drive had been renamed at some point.

### -C, --check-connectivity
Verify connectivity to various server components, and display SSL TLS version and hostnames. Where possible, both internal and external interfaces are checked, since
external connections are routed via a reverse proxy through the web server (Apache, IIS, NGINX). Also see the related -N/--network option.

Testing after connecting to a VPN may interfere with the results.

### -D, --data
Using values based on the last relevant message in the Event log, display the current database directories being used and their sizes, splitting out any
optional external container directories.

The total size values for Default and Secure folders does not include the enclosed RC_Data_FMS folders, which are totaled separately.

### --dir
Print the directory path for the given log name. Could be used in shell command like this:
`cd "$(fmslog --dir event)"`
This will change the current directory to the location of the `Event.log` file. The double quotes are needed for macOS because there is a space character in the path.

### -e, --edit
Opens a log file in an editor. If the standard shell environment variable $EDITOR is set for the user, the file will be opened using that command.

Next, attempt to open using a GUI editor. On macOS, first check that there is a user logged in to the desktop, and if so, open the log file using TextEdit. For Windows, it will open the file using Notepad.

Finally, on Ubuntu and macOS, it will attempt to open the log using the Terminal based nano text editor.

### -f, --filter
For any subsequent logs, only display messages matching the given regular expression (regex).

Filtering will happen before any -n/--number limits are applied, or simplification if using --succinct.

The version of regex expressions used is similar to Perl's regex (often called PCRE), but is specific to Python.

### -h, --head
Display the start of the specified log files instead of its end (tail).

### -H, --headers-off
Disable the printing of any log column headers the command may use, and don't skip any column headers present in the log files.

Normally, unless tailing a log or printing a log that does not have any fixed columns, the command includes its own column header as the first line for each log.

### -i, --ignore-case
If using the -f/--filter option, this option will cause any pattern searches to be case insensitive.

### -L, --list
List all log names and paths for the current platform. For logs that are present, list their creation and modification timestamps and their size.
Any FMS crash reports are also listed here.

### -n, --number
Number of log message lines or screens to print. For screens, add 's' as a suffix, e.g. '-n 2s' for two screens. Since some messages may not fit current screen size
you may want to use the --truncate option to have an exact fit.

### -N, --network
List ports in use by FileMaker's processes.

### -P, --process-info
Display metrics for all processes running under the fmserver user. Metrics include process ID, CPU & memory usage, and process start time.

### -s, --succinct
Shorten the output of log lines where possible. This includes things like redundant time zones and host names, and shortening some values (eg, Warning becomes Warn).

### -S, --set VERB NOUN
Change FMS configuration options. It takes two parameters, a noun and a verb. Currently, verbs are `enable` or `disable`.
The supported nouns are:
- `debuglogging`: detailed FMS logs such as fmsDebug.log; This can significantly slow down some server operations and quickly create large log files
- `clientstats`: user specific statistics for each log interval
- `serverstats`: database engine statistics
- `topcallstats`: statistics for top 25 calls

### -t, --tail
Print messages as they are added to log files until user cancels with Ctrl-C.

Use the form `--tail=<seconds>` to set how many seconds to wait between checks for new data.

### --truncate
Remove any output from the end of the line that would cause a line wrap for the current screen width.

### -V, --version
Print version of fmslog command and FileMaker Server components.

---

![alt](display_logs.png?raw=true "Display Logs")

![alt](connectivity_check.png?raw=true "Connectivity Test")