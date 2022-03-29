// DEW HEATER (it version)
// Copyright (c) 2021-2022 Società Astronomica G.V. Schiaparelli
// Paolo Galli <paolo97gll@gmail.com>

const UPDATE_TIME = 5000;

function start() {
    setTimeout(getStatus, 0);
    setInterval(getStatus, UPDATE_TIME);
}

function getStatus() {
    let request = new Request(`api?json=${encodeURIComponent(JSON.stringify({ "cmd": "status" }))}`);
    fetchTimeout(request)
        .then(rsp => {
            // update page
            document.getElementById("auto").innerHTML = `Modalità automatica: ${rsp["auto"] ? "ON" : "OFF"}`;
            document.getElementById("input-auto").value = `Clicca per ${rsp["auto"] ? "manuale" : "automatico"}`;
            document.getElementById("input-auto").disabled = false;
            document.getElementById("main").innerHTML = `Telescopio principale: ${rsp["telescope"]["main"] ? "ON" : "OFF"}`;
            document.getElementById("input-main").className = rsp["telescope"]["main"] ? "green" : "red";
            document.getElementById("input-main").value = rsp["auto"] ? `Fascia ${rsp["telescope"]["main"] ? "accesa" : "spenta"}` : `Clicca per ${rsp["telescope"]["main"] ? "spegnere" : "accendere"}`;
            document.getElementById("input-main").disabled = rsp["auto"];
            document.getElementById("guide").innerHTML = `Telescopio di guida: ${rsp["telescope"]["guide"] ? "ON" : "OFF"}`;
            document.getElementById("input-guide").className = rsp["telescope"]["guide"] ? "green" : "red";
            document.getElementById("input-guide").value = rsp["auto"] ? `Fascia ${rsp["telescope"]["guide"] ? "accesa" : "spenta"}` : `Clicca per ${rsp["telescope"]["guide"] ? "spegnere" : "accendere"}`;
            document.getElementById("input-guide").disabled = rsp["auto"];
        })
        .catch(error => {
            console.trace(`An error has occured: ${error.message}`);
            // update page with default
            document.getElementById("auto").innerHTML = "Modalità automatica: ND";
            document.getElementById("input-auto").value = "Non disponibile";
            document.getElementById("input-auto").disabled = true;
            document.getElementById("main").innerHTML = "Telescopio principale: ND";
            document.getElementById("input-main").className = "gray";
            document.getElementById("input-main").value = "Non disponibile";
            document.getElementById("input-main").disabled = true;
            document.getElementById("guide").innerHTML = "Telescopio di guida: ND";
            document.getElementById("input-guide").className = "gray";
            document.getElementById("input-guide").value = "Non disponibile";
            document.getElementById("input-guide").disabled = true;
        });
}

function toggleMain() {
    // decide final status
    let text = document.getElementById("main").innerHTML;
    if (text == "Telescopio principale: ON") {
        var status = false;
    } else if (text == "Telescopio principale: OFF") {
        var status = true;
    } else {
        alert("Errore: impossibile inoltrare la richiesta.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "telescope": { "main": status } } });
}

function toggleGuide() {
    // decide final status
    let text = document.getElementById("guide").innerHTML;
    if (text == "Telescopio di guida: ON") {
        var status = false;
    } else if (text == "Telescopio di guida: OFF") {
        var status = true;
    } else {
        alert("Errore: impossibile inoltrare la richiesta.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "telescope": { "guide": status } } });
}

function toggleAuto() {
    // decide final status
    let text = document.getElementById("auto").innerHTML;
    if (text == "Modalità automatica: ON") {
        var status = false;
    } else if (text == "Modalità automatica: OFF") {
        var status = true;
    } else {
        alert("Errore: impossibile inoltrare la richiesta.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "auto": status } });
}

function sendCommand(command) {
    let request = new Request(`api?json=${encodeURIComponent(JSON.stringify(command))}`);
    fetchTimeout(request)
        .then(rsp => {
            if (rsp != "done") throw new Error(`Wrong response from backend: ${rsp}`);
            getStatus();
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
