async function loadItems(){return(await fetch("/api/items")).json()}
async function loadUser(id){return(await fetch(`/api/users/${id}`)).json()}
async function loadOrders(){return(await fetch("https://api.example.test/v1/orders?limit=5")).json()}
//# sourceMappingURL=app.js.map
