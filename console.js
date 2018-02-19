
var ws = undefined;
var log;
var blacklist;
var table;
table = document.getElementById('logtable');

function init(){
    console.log("ON LOAD");
    document.getElementById("status").innerHTML = "[Connecting ...]";
    websocket();

    log = document.getElementById("log");
    blacklist = document.getElementById("blacklist");
}

function black(){
    var val = document.getElementById("blacklist_in").value;
    console.log(val);
    sendMessage(val);
}

function websocket(){
    ws = new WebSocket("ws://localhost:8008");
    ws.binaryType = "string";
    ws.onopen = function(evt) { onOpen(evt) };
    ws.onclose = function(evt) { onClose(evt) };
    ws.onmessage = function(evt) { onMessage(evt) };
    ws.onerror = function(evt) { onError(evt) };
}

function onOpen(evt){
    console.log("Connected!");
    document.getElementById("status").innerHTML = "[Connected]";
    sendMessage("TEST");
};


function onMessage(evt){
    console.log("Message is received...");
    var message = evt.data;
    console.log(message);
    var parts = message.split('~');
    console.log(parts);
    updateRow(parts[0], parts[1], parts[2]);

};

function onClose(evt){
    console.log("Connection is closed...");
    document.getElementById("status").innerHTML = "[Disconnected]";
};

function onError(evt){
    console.log("ERROR: "+evt.data);
}

function sendMessage(message){
    console.log("sending: "+message);
    ws.binaryType = "ArrayBuffer";
    ws.send(message);
//    writeTo("SENT: " + message, blacklist);
}

function updateRow(opcode, conn, message){
    switch(opcode){
    case 'M':
        insertMessage(conn, message);
        break;
    case 'N':
        newRow(conn);
        break;
    case 'C':
        insertClosed(conn);
        break;
    case 'B':
        writeTo(conn, blacklist);
        break;
    }
}

function newRow(message){
    console.log(table);
    var row = table.insertRow();
    var cell = row.insertCell(0);
    var newText = document.createTextNode(message);
    cell.appendChild(newText);
    //cell.innerHTML(message);
    var time = document.createTextNode(new Date().timeNow());
    var cell2 = row.insertCell(1);
    cell2.appendChild(time);
    cell = row.insertCell(2);
    newText = document.createTextNode('-');
    cell.appendChild(newText);
    cell = row.insertCell(3);
    newText = document.createTextNode('-');
    cell.appendChild(newText);
}

function insertMessage(conn, message){
    var rows = $("tr:contains("+conn+")");
    var row = rows[rows.length-1];
    if(row){
        row.cells[2].childNodes[0].nodeValue = message;
    }

}

function insertClosed(conn){
//    console.log("CLOSE "+conn);
    var rows = $("tr:contains("+conn+")");
    var row = rows[rows.length-1];
    console.log(row);
    if(row){
        row.cells[3].childNodes[0].nodeValue = new Date().timeNow();
    }
}

function writeTo(message, div){
    var pre = document.createElement("p");
    pre.style.wordWrap = "break-word";
    pre.innerHTML = message;
    div.appendChild(pre);
}

Date.prototype.timeNow = function () {
    return ((this.getHours() < 10)?"0":"") + this.getHours() +":"+ ((this.getMinutes() < 10)?"0":"") + this.getMinutes() +":"+ ((this.getSeconds() < 10)?"0":"") + this.getSeconds();
}

var btn = document.getElementById('init');
btn.addEventListener("click", init, false);
