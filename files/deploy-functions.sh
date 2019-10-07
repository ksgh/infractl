#!/usr/bin/env bash

getdate () {
    echo "$(date "+%x %l:%M:%S %p")"
}

mynotice () {
    [ -f "$LOGFILE" ] && {
        [ -n "$1" ] && echo "NOTICE ($APP_NAME): $(getdate): $1" | tee -a $LOGFILE
    } || {
        [ -n "$1" ] && echo "NOTICE: $(getdate): $1"
    }
}

mywarning () {
    [ -f "$LOGFILE" ] && {
        [ -n "$1" ] && echo "WARNING ($APP_NAME): $(getdate): $1" | tee -a $LOGFILE
    } || {
        [ -n "$1" ] && echo "WARNING: $(getdate): $1"
    }
}

myerror () {
    [ -f "$LOGFILE" ] && {
        [ -n "$1" ] && echo "ERROR ($APP_NAME): $(getdate): $1" | tee -a $LOGFILE
    } || {
        [ -n "$1" ] && echo "ERROR: $(getdate): $1" >&2
    }
}

in_array () {
    local needle="$1"; shift
    local ar="$@"

    [ "${#ar[@]}" -le 0 ] && return 1

    for i in ${ar[@]}
    do
        [ "$needle" = "$i" ] && return 0
    done
    return 1
}

restart_docker_rabbit_services () {
    local services=$@
    shift $((OPTIND-1))
    for sn in ${services[@]}
    do
        mynotice "Restarting Service: $sn"
        docker service update --force $sn --detach
    done
}

restart_systemd_service () {
    local _service="$1"; shift
    local _verbose="$1"; shift
    [[ -z "$_service" ]] && myerror "Service to restart is required" && return 1

    systemctl restart $_service &> /dev/null && {
        mynotice "$_service successfully restarted"
        [[ -n "$_verbose" ]] && systemctl status $_service -l
        return 0
    }

    myerror "Restarting $_service failed!"
    systemctl status $_service -l
    return 1
}

restart_airflow () {
    local _subservice="$1"; shift
    [ -z "$_subservice" ] && myerror "we need to know what part of airflow to restart!!" && return 1

    local _af_service="airflow-${_subservice}"

    if restart_systemd_service "$_af_service"; then
        ## NOT FAILING HERE BECAUSE THIS IS AN ASYNCHRONOUS SERVICE !!
        ## The application (at this time) will not fail because we could not restart airflow
        ## HOWEVER - we should have some sort of a notification mechanism here.
        mywarning "This does NOT fail a deployment at this time!"
    fi
    return 0
}

get_supermgr () {
    which supermgr 2>/dev/null
    return $?
}

halt_supervisord_prgms () {
    local _smgr="$(get_supermgr)"

    [[ -z "$_smgr)" ]] && return 1

    $_smgr --save && {
        mynotice "Successfully saved supervisord worker states"
    } || {
        mywarning "Something wasn't right with saving supervisord worker state, reload might not work!"
    }
    $_smgr --stop all all && {
        mynotice "All supervisord jobs have been cleanly stopped"
    }
    restart_systemd_service "supervisord"
}

start_supervisord_prgms () {
    local _smgr="$(get_supermgr)"

    [[ -z "$_smgr)" ]] && return 1

    $_smgr --reload && {
        mynotice "Successfully reloaded supervisord worker states"
    } || {
        mywarning "Something wasn't right with reloading supervisord worker states!"
    }
}

link_app_log_dir () {
    local _source="$1"; shift
    local _dest="$1"; shift
    local _code_owner="${1:-nginx}"; shift
    local _code_group=-"${1:-nginx}"; shift

    [[ ! -d "$_source" ]] && mkdir -p "$_source"

    chown $_code_owner:$_code_group "$_source"

    [[ -d "$_dest" ]] && \rm -rf $_dest || return 1

    ln -sfn "$_source" "$_dest" && {
        chown -h $_code_owner:$_code_group "$_dest"
        return 0
    }
    return 1
}

restore_app_log_dir () {
    local _dir="$1"; shift
    [[ -z "$_dir" ]] && return 0
    [[ ! -d "$_dir" ]] && {
        mkdir -p "$_dir" || return 1
    }
    return 0
}