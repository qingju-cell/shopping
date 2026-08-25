const svg = (w: number, h: number, text: string) => {
  const svgStr = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
  <rect width="100%" height="100%" fill="#f0f0f0"/>
  <text x="50%" y="50%" font-family="Arial, sans-serif" font-size="14" fill="#909399" text-anchor="middle" dominant-baseline="middle">${text}</text>
</svg>`
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgStr)
}

export const PLACEHOLDER_IMG = {
  '60x60': svg(60, 60, '暂无图'),
  '80x80': svg(80, 80, '暂无图'),
  '300x300': svg(300, 300, '暂无图片'),
  '500x500': svg(500, 500, '暂无图片'),
}