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
            const result = await resp.json();
            this.showToast(result.message, !result.success);
            return result;
        } catch (e) {
            this.showToast("Erreur réseau: " + e.message, true);
            return { success: false, message: e.message };
        }
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

            overlay.querySelector(".btn-cancel").onclick = () => {
                overlay.remove();
                resolve(false);
            };
            overlay.querySelector(".btn-danger").onclick = () => {
                overlay.remove();
                resolve(true);
            };
            overlay.onclick = (e) => {
                if (e.target === overlay) {
                    overlay.remove();
                    resolve(false);
                }
            };
        });
    },

    async killProcess(pid, name, signal) {
        signal = signal || "SIGTERM";
        const confirmed = await this.confirm(
            `Envoyer ${signal} au processus <strong>${name || "?"}</strong> (PID ${pid}) ?`
        );
        if (confirmed) {
            await this.post("/api/actions/kill", { pid: pid, signal: signal });
        }
    },

    async blockPort(spec, protocol, direction) {
        protocol = protocol || "tcp";
        direction = direction || "in";
        const confirmed = await this.confirm(
            `Bloquer le port <strong>${spec}</strong> (${protocol}, ${direction}) ?`
        );
        if (confirmed) {
            await this.post("/api/actions/block-port", { spec, protocol, direction });
        }
    },

    async unblockPort(spec, protocol, direction) {
        protocol = protocol || "tcp";
        direction = direction || "in";
        await this.post("/api/actions/unblock-port", { spec, protocol, direction });
    },

    async blockIp(spec, direction) {
        direction = direction || "in";
        const confirmed = await this.confirm(
            `Bloquer l'IP <strong>${spec}</strong> (${direction}) ?`
        );
        if (confirmed) {
            await this.post("/api/actions/block-ip", { spec, direction });
        }
    },

    async unblockIp(spec, direction) {
        direction = direction || "in";
        await this.post("/api/actions/unblock-ip", { spec, direction });
    },

    async serviceAction(name, action) {
        const destructive = ["stop", "restart"].includes(action);
        if (destructive) {
            const confirmed = await this.confirm(
                `Exécuter <strong>${action}</strong> sur le service <strong>${name}</strong> ?`
            );
            if (!confirmed) return;
        }
        await this.post("/api/actions/service", { name, action });
    },
};
