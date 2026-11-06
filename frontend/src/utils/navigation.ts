/** Полная загрузка страницы (не SPA-переход); вынесено в функцию, чтобы её можно было подменить в тестах. */
export const hardNavigate = (url: string) => window.location.assign(url);
