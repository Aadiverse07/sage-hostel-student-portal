// ========================================
// SAGE HOSTEL PORTAL
// JavaScript
// ========================================

// Live Date & Time

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

if (date && time) {
    updateClock();
    setInterval(updateClock,1000);
}

// ========================================
// Show Password
// ========================================

const password =
document.getElementById("password");

const toggle =
document.getElementById("togglePassword");

if (toggle && password) {
toggle.addEventListener("click",()=>{

    if(password.type==="password"){

        password.type="text";

        toggle.innerHTML=
        '<i class="fa-solid fa-eye-slash"></i>';

    }

    else{

        password.type="password";

        toggle.innerHTML=
        '<i class="fa-solid fa-eye"></i>';

    }

});
}

// ========================================
// Login Animation
// ========================================

const form =
document.getElementById("loginForm");

const button =
document.querySelector(".login-btn");

if (form && button) {
form.addEventListener("submit",function(e){

    // Show a loading state, then let the form submit for real.
    button.innerHTML =
    '<i class="fa-solid fa-spinner fa-spin"></i> Authenticating...';

    button.disabled=true;

    button.style.opacity=".85";

});
}

// ========================================
// Input Animation
// ========================================

const inputs =
document.querySelectorAll("input");

inputs.forEach(input=>{

    input.addEventListener("focus",()=>{

        input.parentElement.style.transform="scale(1.03)";

    });

    input.addEventListener("blur",()=>{

        input.parentElement.style.transform="scale(1)";

    });

});

// ========================================
// Card Tilt Effect
// ========================================

const card =
document.querySelector(".login-card");

if (card) {
document.addEventListener("mousemove",(e)=>{

    let x =
    (window.innerWidth/2-e.pageX)/35;

    let y =
    (window.innerHeight/2-e.pageY)/35;

    card.style.transform=
    `rotateY(${x}deg) rotateX(${-y}deg)`;

});

document.addEventListener("mouseleave",()=>{

    card.style.transform=
    "rotateX(0deg) rotateY(0deg)";

});
}

// ========================================
// Fade In
// ========================================

window.onload=()=>{

    document.body.style.opacity="1";

};