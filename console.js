
var ws = undefined;
var log;
var blacklist;
var table;
var closeCol = 3;
var msgCol = 2;
var bandwCal = 4;
table = document.getElementById('logtable');

//Init connection to management console backend
function init(){
    console.log("ON LOAD");
    document.getElementById("status").innerHTML = "[Connecting ...]";
    websocket();

    log = document.getElementById("log");
    blacklist = document.getElementById("blacklist");
}

//Block the url
function black(){
    var val = document.getElementById("blacklist_in").value;
    writeTo(val, blacklist); //write back on screen
    sendMessage(val); //send to backend
}

//connect the websocket
function websocket(){
    ws = new WebSocket("ws://localhost:8008");
    ws.binaryType = "string";
    ws.onopen = function(evt) { onOpen(evt) };
    ws.onclose = function(evt) { onClose(evt) };
    ws.onmessage = function(evt) { onMessage(evt) };
    ws.onerror = function(evt) { onError(evt) };
}

//On open update connected status
function onOpen(evt){
    console.log("Connected!");
    document.getElementById("status").innerHTML = "[Connected]";
};

//On message update the tables accordingly
function onMessage(evt){
    var message = evt.data;
    var parts = message.split('~');
    updateRow(parts[0], parts[1], parts[2]);

};

//On close update connected status
function onClose(evt){
    console.log("Connection is closed...");
    document.getElementById("status").innerHTML = "[Disconnected]";
};

function onError(evt){
    console.log("ERROR: "+evt.data);
}

//send massage over websocket
function sendMessage(message){
    console.log("sending: "+message);
    ws.binaryType = "ArrayBuffer";
    ws.send(message);
}

//Update the correct row/collum according to opcode
function updateRow(opcode, conn, message){
    switch(opcode){
    case 'N': // new url
        newRow(conn, message);
        break;
    case 'C': // url closed
        insertInColumn(conn, message, closeCol);
        break;
    case 'M': // new message (only on debug mode)
        insertInColumn(conn, message, msgCol);
        break;
    case 'W': // inital bandwidth for connection
        insertInColumn(conn, message, bandwCal);
        break;
    case 'B': // add to black list
        writeTo(conn, blacklist);
        break;
    }
}

// create a new row in the table for connection
function newRow(conn, message){
    console.log(table);
    var row = table.insertRow();
    var cell = row.insertCell(0);
    var newText = document.createTextNode(conn);
    cell.appendChild(newText);
    var time = document.createTextNode(message);
    var cell2 = row.insertCell(1);
    cell2.appendChild(time);
    for(var i=2; i<=4; i++){
        cell = row.insertCell(i);
        newText = document.createTextNode('-');
        cell.appendChild(newText);
    }
}

// insert the message in the row given by conn (connection url)
//   col gives the column to insert the message to
function insertInColumn(conn, message, col){
    var rows = $("tr:contains("+conn+")");
    var row = rows[rows.length-1];
    if(row){
        row.cells[col].childNodes[0].nodeValue = message;
    }

}

// write to div (used for blacklist)
function writeTo(message, div){
    var pre = document.createElement("p");
    pre.style.wordWrap = "break-word";
    pre.innerHTML = message;
    div.appendChild(pre);
}

// initialise websocket connection on button click
var btn = document.getElementById('init');
btn.addEventListener("click", init, false);
