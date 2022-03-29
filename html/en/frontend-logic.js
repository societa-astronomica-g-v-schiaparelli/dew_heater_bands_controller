// DEW HEATER (en version)
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
            document.getElementById("auto").innerHTML = `Automatic mode: ${rsp["auto"] ? "ON" : "OFF"}`;
            document.getElementById("input-auto").value = `Click for ${rsp["auto"] ? "manual" : "automatic"} mode`;
            document.getElementById("input-auto").disabled = false;
            document.getElementById("main").innerHTML = `Main telescope: ${rsp["telescope"]["main"] ? "ON" : "OFF"}`;
            document.getElementById("input-main").className = rsp["telescope"]["main"] ? "green" : "red";
            document.getElementById("input-main").value = rsp["auto"] ? `Heater ${rsp["telescope"]["main"] ? "on" : "off"}` : `Click to ${rsp["telescope"]["main"] ? "off" : "on"}`;
            document.getElementById("input-main").disabled = rsp["auto"];
            document.getElementById("guide").innerHTML = `Guide telescope: ${rsp["telescope"]["guide"] ? "ON" : "OFF"}`;
            document.getElementById("input-guide").className = rsp["telescope"]["guide"] ? "green" : "red";
            document.getElementById("input-guide").value = rsp["auto"] ? `Heater ${rsp["telescope"]["guide"] ? "on" : "off"}` : `Click to ${rsp["telescope"]["guide"] ? "off" : "on"}`;
            document.getElementById("input-guide").disabled = rsp["auto"];
        })
        .catch(error => {
            console.trace(`An error has occured: ${error.message}`);
            // update page with default
            document.getElementById("auto").innerHTML = "Automatic mode: ND";
            document.getElementById("input-auto").value = "Unavailable";
            document.getElementById("input-auto").disabled = true;
            document.getElementById("main").innerHTML = "Main telescope: ND";
            document.getElementById("input-main").className = "gray";
            document.getElementById("input-main").value = "Unavailable";
            document.getElementById("input-main").disabled = true;
            document.getElementById("guide").innerHTML = "Guide telescope: ND";
            document.getElementById("input-guide").className = "gray";
            document.getElementById("input-guide").value = "Unavailable";
            document.getElementById("input-guide").disabled = true;
        });
}

function toggleMain() {
    // decide final status
    let text = document.getElementById("main").innerHTML;
    if (text == "Main telescope: ON") {
        var status = false;
    } else if (text == "Main telescope: OFF") {
        var status = true;
    } else {
        alert("Error: cannot send request.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "telescope": { "main": status } } });
}

function toggleGuide() {
    // decide final status
    let text = document.getElementById("guide").innerHTML;
    if (text == "Guide telescope: ON") {
        var status = false;
    } else if (text == "Guide telescope: OFF") {
        var status = true;
    } else {
        alert("Error: cannot send request.");
        return;
    }
    // make request
    sendCommand({ "cmd": "set", "params": { "telescope": { "guide": status } } });
}

function toggleAuto() {
    // decide final status
    let text = document.getElementById("auto").innerHTML;
    if (text == "Automatic mode: ON") {
        var status = false;
    } else if (text == "Automatic mode: OFF") {
        var status = true;
    } else {
        alert("Error: cannot send request.");
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
