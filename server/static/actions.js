"use strict";

const Actions = {
    getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    },

    showToast(message, isError) {
        const toast = document.createElement("div");
        toast.className = "toast " + (isError ? "toast-error" : "toast-success");
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.classList.add("toast-visible"), 10);
        setTimeout(() => {
            toast.classList.remove("toast-visible");
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    },

    async post(endpoint, data) {
        try {
            const resp = await fetch(endpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": this.getCsrfToken(),
                },
                body: JSON.stringify(data),
            });
            // Session expirée — Flask redirige vers /login avec 200 après follow
            const ct = resp.headers.get("content-type") || "";
            if (!ct.includes("application/json")) {
                this.showToast("Session expirée — reconnexion...", true);
                setTimeout(() => { window.location.href = "/login"; }, 1500);
                return { success: false, message: "Session expirée" };
            }
            const result = await resp.json();
            this.showToast(result.message, !result.success);
            return result;
        } catch (e) {
            this.showToast("Erreur réseau: " + e.message, true);
            return { success: false, message: e.message };
        }
    },

    /*
     * Si window.TARGET_HOSTNAME est défini, l'action est envoyée à l'agent
     * distant via la queue de commandes (/api/commands/<hostname>).
     * Sinon elle s'exécute localement sur le serveur (/api/actions/*).
     */
    async _dispatch(action, params) {
        const host = window.TARGET_HOSTNAME;
        if (host) {
            return await this.post(
                "/api/commands/" + encodeURIComponent(host),
                { action, params }
            );
        }
        return await this.post("/api/actions/" + action, params);
    },

    confirm(message) {
        return new Promise((resolve) => {
            const overlay = document.createElement("div");
            overlay.className = "modal-overlay";
            overlay.innerHTML = `
                <div class="modal-box">
                    <p class="modal-message">${message}</p>
                    <div class="modal-buttons">
                        <button class="btn btn-cancel">Annuler</button>
                        <button class="btn btn-danger">Confirmer</button>
                    </div>
                </div>`;
            document.body.appendChild(overlay);
            setTimeout(() => overlay.classList.add("modal-visible"), 10);

            overlay.querySelector(".btn-cancel").onclick = () => { overlay.remove(); resolve(false); };
            overlay.querySelector(".btn-danger").onclick = () => { overlay.remove(); resolve(true); };
            overlay.onclick = (e) => { if (e.target === overlay) { overlay.remove(); resolve(false); } };
        });
    },

    async killProcess(pid, name, signal) {
        signal = signal || "SIGTERM";
        const host = window.TARGET_HOSTNAME ? ` sur <strong>${window.TARGET_HOSTNAME}</strong>` : "";
        const confirmed = await this.confirm(
            `Envoyer ${signal} au processus <strong>${name || "?"}</strong> (PID ${pid})${host} ?`
        );
        if (confirmed) {
            await this._dispatch("kill", { pid: pid, signal: signal });
        }
    },

    async blockPort(spec, protocol, direction) {
        protocol = protocol || "tcp";
        direction = direction || "in";
        const host = window.TARGET_HOSTNAME ? ` sur <strong>${window.TARGET_HOSTNAME}</strong>` : "";
        const confirmed = await this.confirm(
            `Bloquer le port <strong>${spec}</strong> (${protocol}, ${direction})${host} ?`
        );
        if (confirmed) {
            await this._dispatch("block-port", { spec, protocol, direction });
        }
    },

    async unblockPort(spec, protocol, direction) {
        protocol = protocol || "tcp";
        direction = direction || "in";
        await this._dispatch("unblock-port", { spec, protocol, direction });
    },

    async blockIp(spec, direction) {
        direction = direction || "in";
        const host = window.TARGET_HOSTNAME ? ` sur <strong>${window.TARGET_HOSTNAME}</strong>` : "";
        const confirmed = await this.confirm(
            `Bloquer l'IP <strong>${spec}</strong> (${direction})${host} ?`
        );
        if (confirmed) {
            await this._dispatch("block-ip", { spec, direction });
        }
    },

    async unblockIp(spec, direction) {
        direction = direction || "in";
        await this._dispatch("unblock-ip", { spec, direction });
    },

    async serviceAction(name, action) {
        const destructive = ["stop", "restart"].includes(action);
        if (destructive) {
            const host = window.TARGET_HOSTNAME ? ` sur <strong>${window.TARGET_HOSTNAME}</strong>` : "";
            const confirmed = await this.confirm(
                `Exécuter <strong>${action}</strong> sur le service <strong>${name}</strong>${host} ?`
            );
            if (!confirmed) return;
        }
        await this._dispatch("service", { name, action });
    },
};
