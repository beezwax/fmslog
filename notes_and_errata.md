# fmslog notes & errata
## ideas, problems, etc.


## POSSIBLE NEW OPTIONS
* non-standard install location
* 'top' or iostat like option
* scan all logs for recent errors, exceptions, etc.
* summarize results where possible (eg, count, min, max, sum)?
* convert table IDs
* paged output
* remote/external log source via SSH
* for succinct mode, change 'Information' to 'Info' and 'Warning' to 'Warn' (Error will then be longest)

EXAMPLES OF UNIMPLEMENTED USAGE
	fmslog --ssh simon@server.beezwax.net topcall  # if using user's default 'SSH key

## NOTES

Reset repo:  `git fetch origin main; git reset --hard origin/main`

