// DEW HEATER (https://github.com/societa-astronomica-g-v-schiaparelli/dew_heater_bands_controller)
// Copyright (c) 2021-2022 Società Astronomica G.V. Schiaparelli
// Paolo Galli <paolo.galli@astrogeo.va.it>

const UPDATE_TIME = 5000;

function start() {
    const source = new ReconnectingEventSource("status-sse");
    source.onopen = function (e) {
        console.log("Connection ok, start receiving updates.");
    }
    source.onmessage = function (e) {
        console.log("New update received!");
        const rsp = JSON.parse(e.data);
        document.getElementById("auto").innerText = `Automatic mode: ${rsp["auto"] ? "ON" : "OFF"}`;
        document.getElementById("input-auto").value = `Click for ${rsp["auto"] ? "manual" : "automatic"} mode`;
        document.getElementById("input-auto").disabled = false;
        document.getElementById("main").innerText = `Main telescope: ${rsp["telescope"]["main"] ? "ON" : "OFF"}`;
        document.getElementById("input-main").className = rsp["telescope"]["main"] ? "green" : "red";
        document.getElementById("input-main").value = rsp["auto"] ? `Heater ${rsp["telescope"]["main"] ? "on" : "off"}` : `Click to ${rsp["telescope"]["main"] ? "off" : "on"}`;
        document.getElementById("input-main").disabled = rsp["auto"];
        document.getElementById("guide").innerText = `Guide telescope: ${rsp["telescope"]["guide"] ? "ON" : "OFF"}`;
        document.getElementById("input-guide").className = rsp["telescope"]["guide"] ? "green" : "red";
        document.getElementById("input-guide").value = rsp["auto"] ? `Heater ${rsp["telescope"]["guide"] ? "on" : "off"}` : `Click to ${rsp["telescope"]["guide"] ? "off" : "on"}`;
        document.getElementById("input-guide").disabled = rsp["auto"];
    }
    source.onerror = function (e) {
        if (e.target.readyState != EventSource.OPEN) console.log("Disconnected, retry...");
        else console.log("Error during response handling.");
        document.getElementById("auto").innerText = "Automatic mode: ND";
        document.getElementById("input-auto").value = "Unavailable";
        document.getElementById("input-auto").disabled = true;
        document.getElementById("main").innerText = "Main telescope: ND";
        document.getElementById("input-main").className = "gray";
        document.getElementById("input-main").value = "Unavailable";
        document.getElementById("input-main").disabled = true;
        document.getElementById("guide").innerText = "Guide telescope: ND";
        document.getElementById("input-guide").className = "gray";
        document.getElementById("input-guide").value = "Unavailable";
        document.getElementById("input-guide").disabled = true;
    }
}

function toggleMain() {
    // decide final status
    const text = document.getElementById("main").innerText;
    let status;
    if (text == "Main telescope: ON") {
        status = false;
    } else if (text == "Main telescope: OFF") {
        status = true;
    } else {
        alert("Error: cannot send request.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "telescope": { "main": status } } });
}

function toggleGuide() {
    // decide final status
    const text = document.getElementById("guide").innerText;
    let status;
    if (text == "Guide telescope: ON") {
        status = false;
    } else if (text == "Guide telescope: OFF") {
        status = true;
    } else {
        alert("Error: cannot send request.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "telescope": { "guide": status } } });
}

function toggleAuto() {
    // decide final status
    const text = document.getElementById("auto").innerText;
    let status;
    if (text == "Automatic mode: ON") {
        status = false;
    } else if (text == "Automatic mode: OFF") {
        status = true;
    } else {
        alert("Error: cannot send request.");
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
            alert("Error: cannot send request.");
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
