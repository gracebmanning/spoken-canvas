const ws = new WebSocket('ws://localhost:5000');

const controlTDSlider = document.getElementById('controlTD');
const controlledByTDSlider = document.getElementById('controlledByTD');

ws.addEventListener('open', (event) => {
    console.log('Connected to the server!')
})

ws.addEventListener('message', (message) => {
    if(message.data == 'ping'){
        ws.send('pong');
        return
    }

    let data = JSON.parse(message.data);
    if('slider1' in data){
        let val = data['slider1'] ;
        controlledByTDSlider.value = val * 100.0;
    }
    console.log(data);
});

ws.addEventListener('error', (error) => {
    console.error(error);
});

ws.addEventListener('close', (event) => {
    console.log('Connection closed.')
});

controlTDSlider.addEventListener('input', (event) => {
    const value = event.target.value / 100.0;
    const dataObject = {slider1: value};
    ws.send(JSON.stringify(dataObject)); 
});