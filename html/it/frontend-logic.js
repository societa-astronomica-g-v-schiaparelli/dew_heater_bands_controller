// DEW HEATER (https://github.com/societa-astronomica-g-v-schiaparelli/RCM-dew_heater) (it version)
// Copyright (c) 2021-2022 Società Astronomica G.V. Schiaparelli
// Paolo Galli <paolo97gll@gmail.com>

function start() {
    const source = new ReconnectingEventSource("status-sse");
    source.onopen = function (e) {
        console.log("Connection ok, start receiving updates.");
    }
    source.onmessage = function (e) {
        console.log("New update received!");
        const rsp = JSON.parse(e.data);
        document.getElementById("auto").innerText = `Modalità automatica: ${rsp["auto"] ? "ON" : "OFF"}`;
        document.getElementById("input-auto").value = `Clicca per ${rsp["auto"] ? "manuale" : "automatico"}`;
        document.getElementById("input-auto").disabled = false;
        document.getElementById("main").innerText = `Telescopio principale: ${rsp["telescope"]["main"] ? "ON" : "OFF"}`;
        document.getElementById("input-main").className = rsp["telescope"]["main"] ? "green" : "red";
        document.getElementById("input-main").value = rsp["auto"] ? `Fascia ${rsp["telescope"]["main"] ? "accesa" : "spenta"}` : `Clicca per ${rsp["telescope"]["main"] ? "spegnere" : "accendere"}`;
        document.getElementById("input-main").disabled = rsp["auto"];
        document.getElementById("guide").innerText = `Telescopio di guida: ${rsp["telescope"]["guide"] ? "ON" : "OFF"}`;
        document.getElementById("input-guide").className = rsp["telescope"]["guide"] ? "green" : "red";
        document.getElementById("input-guide").value = rsp["auto"] ? `Fascia ${rsp["telescope"]["guide"] ? "accesa" : "spenta"}` : `Clicca per ${rsp["telescope"]["guide"] ? "spegnere" : "accendere"}`;
        document.getElementById("input-guide").disabled = rsp["auto"];
    }
    source.onerror = function (e) {
        if (e.target.readyState != EventSource.OPEN) console.log("Disconnected, retry...");
        else console.log("Error during response handling.");
        document.getElementById("auto").innerText = "Modalità automatica: ND";
        document.getElementById("input-auto").value = "Non disponibile";
        document.getElementById("input-auto").disabled = true;
        document.getElementById("main").innerText = "Telescopio principale: ND";
        document.getElementById("input-main").className = "gray";
        document.getElementById("input-main").value = "Non disponibile";
        document.getElementById("input-main").disabled = true;
        document.getElementById("guide").innerText = "Telescopio di guida: ND";
        document.getElementById("input-guide").className = "gray";
        document.getElementById("input-guide").value = "Non disponibile";
        document.getElementById("input-guide").disabled = true;
    }
}

function toggleMain() {
    // decide final status
    const text = document.getElementById("main").innerText;
    let status;
    if (text == "Telescopio principale: ON") {
        status = false;
    } else if (text == "Telescopio principale: OFF") {
        status = true;
    } else {
        alert("Errore: impossibile inoltrare la richiesta.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "telescope": { "main": status } } });
}

function toggleGuide() {
    // decide final status
    const text = document.getElementById("guide").innerText;
    let status;
    if (text == "Telescopio di guida: ON") {
        status = false;
    } else if (text == "Telescopio di guida: OFF") {
        status = true;
    } else {
        alert("Errore: impossibile inoltrare la richiesta.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "telescope": { "guide": status } } });
}

function toggleAuto() {
    // decide final status
    const text = document.getElementById("auto").innerText;
    let status;
    if (text == "Modalità automatica: ON") {
        status = false;
    } else if (text == "Modalità automatica: OFF") {
        status = true;
    } else {
        alert("Errore: impossibile inoltrare la richiesta.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "auto": status } });
}

function sendCommand(command) {
    const request = new Request(`api?json=${encodeURIComponent(JSON.stringify(command))}`);
    fetchTimeout(request)
        .then(rsp => {
            if (rsp != "done") throw new Error(`Wrong response from backend: ${rsp}`);
        })
        .catch(error => {
            console.trace(`An error has occured: ${error.message}`);
            alert("Errore: impossibile inoltrare la richiesta.");
        });
}

async function fetchTimeout(url, ms = 3500, { signal, ...options } = {}) {
    const controller = new AbortController();
    const promise = fetch(url, { signal: controller.signal, ...options });
    if (signal) signal.addEventListener("abort", () => controller.abort());
    const timeout = setTimeout(() => controller.abort(), ms);
    const response = await promise.finally(() => clearTimeout(timeout));
    if (!response.ok) throw new Error(`${response.status}, ${response.statusText}`);
    const json = await response.json();
    return json["rsp"];
}
