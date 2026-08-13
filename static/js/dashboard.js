// ==============================
// SAGE HOSTEL DASHBOARD
// dashboard.js
// ==============================

// Loader

window.addEventListener("load", () => {

    setTimeout(() => {

        document.getElementById("loader").style.opacity = "0";

        document.getElementById("loader").style.visibility = "hidden";

    }, 3000);

});

// ==============================
// Live Date & Time
// ==============================

const date = document.getElementById("date");
const time = document.getElementById("time");

function updateClock() {

    const now = new Date();

    date.innerHTML = now.toLocaleDateString("en-IN", {

        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"

    });

    time.innerHTML = now.toLocaleTimeString("en-IN");

}

updateClock();

setInterval(updateClock,1000);

// ==============================
// Sidebar Active Item
// ==============================

const menuItems = document.querySelectorAll(".sidebar li");

menuItems.forEach(item=>{

    item.addEventListener("click",()=>{

        menuItems.forEach(i=>{

            i.classList.remove("active");

        });

        item.classList.add("active");

    });

});

// ==============================
// Card Hover Animation
// ==============================

const cards = document.querySelectorAll(".card");

cards.forEach(card=>{

    card.addEventListener("mousemove",(e)=>{

        const rect = card.getBoundingClientRect();

        const x = e.clientX - rect.left;

        const y = e.clientY - rect.top;

        card.style.background =

        `radial-gradient(circle at ${x}px ${y}px,
        rgba(59,130,246,.45),
        #131d31 70%)`;

    });

    card.addEventListener("mouseleave",()=>{

        card.style.background="#131d31";

    });

});

// ==============================
// Gallery Zoom
// ==============================

const images=document.querySelectorAll(".gallery img");

images.forEach(img=>{

    img.addEventListener("click",()=>{

        img.classList.toggle("zoom");

    });

});

// ==============================
// Welcome Animation
// ==============================

const heading=document.querySelector("header h1");

const text=heading.innerText;

heading.innerHTML="";

let i=0;

function typing(){

    if(i<text.length){

        heading.innerHTML+=text.charAt(i);

        i++;

        setTimeout(typing,60);

    }

}

typing();

// ==============================
// Online Status Animation
// ==============================

const status=document.querySelector(".status");

setInterval(()=>{

    status.style.boxShadow="0 0 20px rgba(34,197,94,.8)";

    setTimeout(()=>{

        status.style.boxShadow="none";

    },600);

},2500);

// ==============================
// Counter Animation
// ==============================

const values=document.querySelectorAll(".card h1");

values.forEach(value=>{

    const target=value.innerText;

    if(!isNaN(target.replace("%",""))){

        let current=0;

        const end=parseInt(target);

        const interval=setInterval(()=>{

            current++;

            if(target.includes("%")){

                value.innerHTML=current+"%";

            }

            else{

                value.innerHTML=current;

            }

            if(current>=end){

                clearInterval(interval);

                value.innerHTML=target;

            }

        },20);

    }

});

// ==============================
// Logout
// ==============================

const logout=document.querySelector(".sidebar li:last-child");

logout.addEventListener("click",()=>{

    const confirmLogout=confirm("Logout from Hostel Portal?");

    if(confirmLogout){

        window.location.href="/logout";

    }

});

// ==============================
// Keyboard Shortcut
// ==============================

document.addEventListener("keydown",(e)=>{

    if(e.key==="Escape"){

        window.scrollTo({

            top:0,

            behavior:"smooth"

        });

    }

});

// ==============================
// Greeting
// ==============================

const hour=new Date().getHours();

let greeting="Welcome";

if(hour<12){

    greeting="Good Morning";

}

else if(hour<17){

    greeting="Good Afternoon";

}

else{

    greeting="Good Evening";

}

setTimeout(()=>{

    const p=document.querySelector("header p");

    p.innerHTML=greeting+" • SAGE University Boys Hostel";

},1200);
