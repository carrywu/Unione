import { onBeforeUnmount, ref } from 'vue';

export function useCountdown(seconds: number, onExpire: () => void) {
  const timeLeft = ref(seconds);
  let timer: number | undefined;

  function start() {
    stop();
    timer = window.setInterval(() => {
      timeLeft.value -= 1;
      if (timeLeft.value <= 0) {
        timeLeft.value = 0;
        stop();
        onExpire();
      }
    }, 1000);
  }

  function stop() {
    if (timer) {
      window.clearInterval(timer);
      timer = undefined;
    }
  }

  function reset(nextSeconds = seconds) {
    timeLeft.value = nextSeconds;
  }

  onBeforeUnmount(stop);

  return { timeLeft, start, stop, reset };
}
