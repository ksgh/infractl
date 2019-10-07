#!/bin/bash

DESTINATION_ROOT=""
BUILD_NUM=""
APP_NAME=""
LIVE_LINK="live"
LOGFILE=""
REAL_PATH=""

CODE_OWNER="nginx"
CODE_GROUP="nginx"

APP_LOG_PERSISTENCE=0
APP_LOG_REAL_PATH_BASE="/var/log/infractl"

DEPLOY_FUNCTIONS="./deploy-functions.sh"

declare -a _errors

while getopts "d:b:a:l:" OPT
do
    case "$OPT" in
        d) DESTINATION_ROOT="$OPTARG" ;;
        b) BUILD_NUM="$OPTARG" ;;
        a) APP_NAME="$OPTARG" ;;
        l) LOGFILE="$OPTARG" ;;
        *) echo "Option: \"$OPT\" not supported" ;;
    esac
done

## be sure we can write to LOGFILE, otherwise unset it so we don't blow chunks
[[ -n "$LOGFILE" ]] && {
    touch $LOGFILE || LOGFILE=""
}

[[ -f "$DEPLOY_FUNCTIONS" ]] || {
    echo "Uh oh... ${DEPLOY_FUNCTIONS} was not found... gotta bail." >&2
    exit 1
}

source "${DEPLOY_FUNCTIONS}" || {
    echo "Somethings blew up sourcing ${DEPLOY_FUNCTIONS}... gotta bail." >&2
    exit 1
}

[[ -z "$DESTINATION_ROOT" ]] && {
    _errors[${#_errors[@]}]="-d (DESTINATION_ROOT) missing"
}
[[ "$((BUILD_NUM+0))" -le 0 ]] && {
    _errors[${#_errors[@]}]="-b (BUILD_NUM) must be provided and cannot be 0"
}
[[ -z "$APP_NAME" ]] && {
    _errors[${#_errors[@]}]="-a (APP_NAME) missing"
}

[[ "${#_errors[@]}" -gt 0 ]] && {
    myerror "Please address errors!"
    for e in "${_errors[@]}"
    do
        myerror "   $e"
    done
    exit 1
}

APP_ROOT="$DESTINATION_ROOT/$APP_NAME"
FRESH_BUILD_PATH="$APP_ROOT/${APP_NAME}-${BUILD_NUM}"
PACKAGE_NAME="$FRESH_BUILD_PATH.tgz"
LIVE_LINK="$APP_ROOT/live"

PERSISTENT_LOG_PATH="$APP_LOG_REAL_PATH_BASE/$APP_NAME"
BUILD_LOG_PATH="$FRESH_BUILD_PATH/app/logs"

cat <<EOF
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~ Before we rip and tear ~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#
#                         APP_ROOT: ${APP_ROOT}
#                 FRESH_BUILD_PATH: ${FRESH_BUILD_PATH}
#                     PACKAGE_NAME: ${PACKAGE_NAME}
#                        LIVE_LINK: ${LIVE_LINK}
#              PERSISTENT_LOG_PATH: ${PERSISTENT_LOG_PATH}
#                   BUILD_LOG_PATH: ${BUILD_LOG_PATH}
#
#                  Docker Detected: $(which docker > /dev/null 2>&1 && echo "Yes" || echo "No")
#                         Services: ${__services[@]}
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
EOF

## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
## Ok here we go
## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

if [[ ! -d "$FRESH_BUILD_PATH" ]]; then
    if [[ -f "$PACKAGE_NAME" ]]; then
        mynotice "Unpacking: $PACKAGE_NAME to: $FRESH_BUILD_PATH"
        cd "$APP_ROOT"
        tar -zxf $PACKAGE_NAME
        \mv $APP_NAME $(basename $FRESH_BUILD_PATH)
    else
        myerror "$PACKAGE_NAME doesn't exist"
        exit 1
    fi
else
    mywarning "$FRESH_BUILD_PATH already exists"
fi

id $CODE_OWNER &> /dev/null && {
    chown -R $CODE_OWNER:$CODE_GROUP $FRESH_BUILD_PATH || {
        mywarning "Unable to chown $FRESH_BUILD_PATH to $CODE_OWNER:$CODE_GROUP"
    }
} || {
    mynotice "$CODE_OWNER doesn't exist on this host..."
}

## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
## this might initially be a directory from when the server was first setup so 
## errors weren't blown when trying to start php-fpm and/or nginx... so test for both,
## but issue a warning just to let us know when this happens. It's about knowing what
## to expect, and when.
## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

[[ -d "$LIVE_LINK" -a ! -h "$LIVE_LINK" ]] && {
    mywarning "$LIVE_LINK is a directory, first run or was something not right?"
    \rm -rf $LIVE_LINK || {
        myerror "Unable to remove $LIVE_LINK! Aborting!"
        exit 1
    }
}

[[ -h "$LIVE_LINK" ]] && {
    REAL_PATH="$(readlink -f $LIVE_LINK)"
}

## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
## This is where we have to link up the logs directory
## and it needs to be done off the fresh build path (the "real" directory) - not the "live" link
## because we don't want to miss any logging that might happen as soon as the symlink is flipped.
## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
[[ "$APP_LOG_PERSISTENCE" -eq 1 ]] && {
    if in_array "$APP_NAME" ${PERSIST_APP_LOGS[@]}; then
        link_app_log_dir "$PERSISTENT_LOG_PATH" "$BUILD_LOG_PATH" && {
            mynotice "Linked the $BUILD_LOG_PATH to $PERSISTENT_LOG_PATH"
        } || {
            mywarning "Error linking $BUILD_LOG_PATH to $PERSISTENT_LOG_PATH, reverting to local directory"
            restore_app_log_dir "$BUILD_LOG_PATH" || {
                myerror "Unable to restore $BUILD_LOG_PATH"
            }
        }
    fi
} || {
    mynotice "Application logs will remain local to the deployment: $BUILD_LOG_PATH"
}
## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

mynotice "Making build $APP_NAME-$BUILD_NUM live now"

## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
## do the symlink so we've got the new code in...
## beware that ln doesn't return proper exit status...
## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
ln -sfn "$FRESH_BUILD_PATH" "$LIVE_LINK" || {
    myerror "Unable to link $FRESH_BUILD_PATH to $LIVE_LINK"
    exit 1
}

LINKED_PATH="$(readlink -f $LIVE_LINK)"

[[ "$LINKED_PATH" == "$FRESH_BUILD_PATH" ]] && {
    mynotice "$LIVE_LINK was successfully linked to $FRESH_BUILD_PATH"
} || {
    myerror "Failed to symlink $LINKED_PATH to $FRESH_BUILD_PATH!"
    exit 1
}
mynotice "$FRESH_BUILD_PATH is live"

## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
## now if we've set this, move it... and reload php-fpm
## if we didn't set this variable, then we didn't have a symlink previously 
## which meant this was a fresh server.

## REAL_PATH != FRESH_BUILD_PATH - there may be a reason why we've sent the same build
## if that is the case, just catch it here
## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##
[[ -n "$REAL_PATH" -a -d "$REAL_PATH" ]] && {
    [[ "$REAL_PATH" = "$FRESH_BUILD_PATH" ]] && {
        mywarning "It looks like you've deployed a build that is already here, so we'll leave it alone"
    } || {
        systemctl status php-fpm &>/dev/null && {
            systemctl reload php-fpm && {
                mynotice "php-fpm successfully reloaded"
            } || {
                myerror "Reloading php-fpm returned bad status! Outputting status..."
                myerror "$(systemctl status php-fpm)"
                exit 1
            }
        } || {
            mynotice "php-fpm is not running, therefore was not reloaded."
        }
    }
}

[[ -f "$PACKAGE_NAME" ]] && {
    \rm -f $PACKAGE_NAME && {
        mynotice "Removed $PACKAGE_NAME"
    } || {
        mywarning "Unable to remove $PACKAGE_NAME"
    }
}

exit 0
