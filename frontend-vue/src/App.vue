<template>
  <main class="app-page">
    <aside class="sidebar">
      <section class="brand-block">
        <div>
          <p class="eyebrow">TripWeave Agent</p>
          <h1>旅程规划助手</h1>
        </div>
        <span class="status-badge" :class="backendOk ? 'ok' : 'error'">
          {{ backendOk ? "服务在线" : "连接检查中" }}
        </span>
      </section>

      <form class="planner-form" @submit.prevent="submitPlan">
        <label>
          目的地
          <input v-model.trim="form.city" autocomplete="off" />
        </label>
        <div class="form-pair">
          <label>
            出发日期
            <input v-model="form.start_date" type="date" />
          </label>
          <label>
            天数
            <input v-model.number="form.days" type="number" min="1" max="10" />
          </label>
        </div>
        <section class="city-stop-editor">
          <div class="editor-heading">
            <span>多城市路线</span>
            <small>{{ requestedTotalDays }} 天</small>
          </div>
          <div v-for="(stop, index) in additionalCities" :key="index" class="city-stop-row">
            <input v-model.trim="stop.city" :placeholder="`第 ${index + 2} 站城市`" />
            <input v-model.number="stop.days" type="number" min="1" max="10" placeholder="天数" aria-label="停留天数" />
            <button type="button" class="icon-button compact-icon" title="删除城市" @click="removeCityStop(index)">
              <Trash2 :size="15" />
            </button>
          </div>
          <button type="button" class="secondary-button add-city-button" @click="addCityStop">
            <Plus :size="15" />
            添加下一站
          </button>
        </section>
        <div class="form-pair">
          <label>
            人数
            <input v-model.number="form.travelers" type="number" min="1" max="20" />
          </label>
          <label>
            预算上限
            <input v-model.number="form.max_budget" type="number" min="0" />
          </label>
        </div>
        <label>
          旅行偏好
          <input v-model.trim="preferenceText" autocomplete="off" placeholder="请输入旅行偏好，可留空" />
        </label>
        <div class="form-pair">
          <label>
            节奏
            <select v-model="form.pace">
              <option value="" disabled>请选择节奏</option>
              <option value="relaxed">轻松</option>
              <option value="moderate">适中</option>
              <option value="intensive">紧凑</option>
            </select>
          </label>
          <label>
            交通
            <select v-model="form.transportation">
              <option value="" disabled>请选择交通方式</option>
              <option value="public transit">公共交通</option>
              <option value="walking first">步行为主</option>
              <option value="taxi">打车为主</option>
            </select>
          </label>
        </div>
        <label>
          住宿偏好
          <select v-model="form.accommodation">
            <option value="" disabled>请选择住宿偏好</option>
            <option value="budget hotel">经济酒店</option>
            <option value="standard hotel">标准酒店</option>
            <option value="boutique hotel">精品酒店</option>
          </select>
        </label>
        <label>
          补充要求
          <textarea v-model.trim="form.special_requirements" rows="3" />
        </label>
        <label class="check-row">
          <input v-model="form.include_packing" type="checkbox" />
          生成行李与穿搭建议
        </label>

        <button class="primary-button" type="submit" :disabled="isRunning">
          <WandSparkles :size="18" />
          {{ isRunning ? "正在规划" : "生成规划" }}
        </button>
      </form>

      <section class="progress-box">
        <div class="progress-head">
          <span>{{ progressText }}</span>
          <strong>{{ progress }}%</strong>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${progress}%` }"></div>
        </div>
        <p v-if="jobId" class="job-id">任务 {{ jobId }}</p>
        <p v-if="plannerError" class="planner-error">{{ plannerError }}</p>
      </section>

    </aside>

    <section class="workspace">
      <header class="workspace-header">
        <div>
          <p class="eyebrow">{{ structuredPlan ? "TRIP PLAN" : "RESULT WORKSPACE" }}</p>
          <h2>{{ planTitle }}</h2>
        </div>
        <div class="header-actions">
          <button type="button" class="icon-button" title="刷新地点" @click="refreshPois">
            <RefreshCw :size="17" />
          </button>
          <button type="button" class="icon-button" title="运行设置" @click="openSettings">
            <Settings :size="17" />
          </button>
          <button type="button" class="icon-button" title="导出 Markdown" :disabled="!job?.content" @click="downloadMarkdown">
            <Download :size="17" />
          </button>
          <button type="button" class="icon-button" title="导出 PDF" :disabled="!structuredPlan || exportingPdf" @click="downloadPdf">
            <FileDown :size="17" />
          </button>
        </div>
      </header>

      <nav class="tabs">
        <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
          <component :is="tab.icon" :size="16" />
          {{ tab.label }}
        </button>
      </nav>

      <section v-show="activeTab === 'overview'" class="trip-showcase">
        <div class="showcase-heading">
          <div>
            <p class="showcase-label">TRIP OVERVIEW</p>
            <h3>{{ structuredPlan?.city || form.city || "下一段旅程" }}</h3>
            <p class="showcase-date">
              {{ form.start_date || "请选择出发日期" }} · {{ planDays }} 天 · {{ form.travelers }} 位旅客
            </p>
          </div>
          <div class="showcase-stats">
            <span><b>{{ showcaseAttractions.length }}</b> 个景点</span>
            <span><b>{{ budgetTotal }}</b> 预计费用</span>
          </div>
        </div>
        <div v-if="showcaseAttractions.length" class="attraction-rail">
          <article
            v-for="(spot, index) in showcaseAttractions"
            :key="`${spot.day}-${index}-${spot.place.name}`"
            class="showcase-card"
            :class="{ featured: focusedShowcaseIndex === index }"
            tabindex="0"
            @mouseenter="focusedShowcaseIndex = index"
            @mouseleave="focusedShowcaseIndex = null"
            @focus="focusedShowcaseIndex = index"
            @blur="focusedShowcaseIndex = null"
            @click="selectShowcaseAttraction(index, spot.place)"
          >
            <div class="showcase-image">
              <img
                v-if="attractionPhoto(spot.place)"
                :src="attractionPhoto(spot.place)"
                :alt="spot.place.name || '景点图片'"
                loading="lazy"
                @error="handleAttractionImageError(spot.place)"
              />
              <div v-else class="showcase-image-fallback">
                <MapPinned :size="30" />
                <span>{{ form.city || "TRIP" }}</span>
              </div>
              <span class="day-chip">DAY {{ spot.day }}</span>
            </div>
            <div class="showcase-card-body">
              <p>{{ spot.place.type || "精选景点" }}</p>
              <h4>{{ spot.place.name || "待定地点" }}</h4>
              <span>{{ spot.place.address || "点击查看地点与当天行程" }}</span>
            </div>
          </article>
        </div>
        <div v-else class="showcase-empty">
          <div>
            <span class="showcase-empty-mark"><MapPinned :size="20" /></span>
            <strong>你的行程画廊会显示在这里</strong>
            <p>填写目的地和出发日期，生成后将展示每日景点、地图和预算。</p>
          </div>
        </div>
        <div v-if="planCities.length > 1" class="showcase-city-strip" aria-label="多城市行程">
          <span v-for="segment in planCities" :key="segment.city">
            {{ segment.city }} <b>{{ segment.days }} 天</b>
          </span>
        </div>
      </section>

      <section v-show="activeTab === 'overview'" class="content-grid">
        <article class="metric-card">
          <span>地点</span>
          <strong>{{ structuredPlan?.city || form.city }}</strong>
        </article>
        <article class="metric-card">
          <span>天数</span>
          <strong>{{ planDays }} 天</strong>
        </article>
        <article class="metric-card">
          <span>预计费用</span>
          <strong>{{ budgetTotal }}</strong>
        </article>
        <article class="metric-card">
          <span>图谱节点</span>
          <strong>{{ graphNodeCount }}</strong>
        </article>

        <section class="panel wide-panel">
          <div class="panel-title">
            <h3>每日安排</h3>
            <span>{{ itineraryDays.length ? "结构化日程" : "等待规划结果" }}</span>
          </div>
          <div v-if="itineraryDays.length" class="day-list">
            <article v-for="day in itineraryDays" :key="day.day" class="day-card">
              <div class="day-card-head">
                <div class="day-card-head-main">
                  <strong>Day {{ day.day }}</strong>
                  <span class="day-city">{{ day.city || form.city }}</span>
                </div>
                <span>{{ weatherLabel(day.day) }}</span>
              </div>
              <div class="day-card-summary">
                <span>{{ day.date || "日期待确认" }}</span>
                <span>{{ day.city || form.city }}</span>
                <span>{{ day.total_minutes || 0 }} 分钟安排</span>
              </div>
              <p class="day-route-summary">{{ day.summary || "按地理位置安排当日路线" }}</p>
              <ul>
                <li
                  v-for="(place, index) in day.attractions"
                  :key="`${day.day}-${index}-${place.name}`"
                  :class="{ highlighted: isHighlightedPoi(place) }"
                  @click="focusPoiFromItinerary(place)"
                >
                  <span class="time">{{ attractionTime(index) }}</span>
                  <div>
                    <b>
                      {{ place.name || "待定地点" }}
                      <span v-if="place.research_source" class="source-badge">攻略推荐</span>
                    </b>
                    <p>{{ place.address || "暂无地址" }}</p>
                  </div>
                  <div class="attraction-thumb" aria-label="景点图片">
                    <img
                      v-if="attractionPhoto(place)"
                      :src="attractionPhoto(place)"
                      :alt="place.name || '景点图片'"
                      loading="lazy"
                      @error="handleAttractionImageError(place)"
                    />
                  </div>
                  <div class="attraction-actions">
                    <button type="button" class="icon-button compact-icon" title="查看景点详情" @click.stop="openAttractionDetails(place)">
                      <Info :size="14" />
                    </button>
                    <button type="button" class="icon-button compact-icon" title="上移景点" @click.stop="moveAttraction(day.day, index, -1)">
                      <ArrowUp :size="14" />
                    </button>
                    <button type="button" class="icon-button compact-icon" title="下移景点" @click.stop="moveAttraction(day.day, index, 1)">
                      <ArrowDown :size="14" />
                    </button>
                  </div>
                </li>
              </ul>
              <div class="day-supporting-info">
                <span>交通：{{ day.transportation || form.transportation || "待确认" }}</span>
                <span v-if="day.meals?.lunch">午餐：{{ day.meals.lunch.name }}</span>
                <span v-if="day.meals?.dinner">晚餐：{{ day.meals.dinner.name }}</span>
                <span v-if="day.hotel">住宿：{{ day.hotel.name }}</span>
              </div>
              <button type="button" class="secondary-button route-edit-button" @click="recalculateDayRoutes(day)">
                <Route :size="14" />
                重算本日路线
              </button>
            </article>
          </div>
          <div v-else class="empty-state">生成规划后会显示按天拆分的行程卡片。</div>
          <section v-if="selectedAttraction" class="attraction-detail-panel">
            <div class="detail-image">
              <img v-if="attractionPhoto(selectedAttraction)" :src="attractionPhoto(selectedAttraction)" :alt="selectedAttraction.name || '景点图片'" />
              <span v-else>暂无图片</span>
            </div>
            <div class="detail-copy">
              <div class="panel-title detail-title">
                <h3>{{ selectedAttraction.name }}</h3>
                <button type="button" class="icon-button compact-icon" title="关闭详情" @click="selectedAttraction = null">×</button>
              </div>
              <p>{{ selectedAttraction.address || "暂无地址" }}</p>
              <div class="detail-facts">
                <span>类型：{{ selectedAttraction.type || "景点" }}</span>
                <span>游览：{{ selectedAttraction.visit_minutes || 120 }} 分钟</span>
                <span v-if="selectedAttraction.rating">评分：{{ selectedAttraction.rating }}</span>
                <span v-if="selectedAttraction.cost">参考消费：{{ selectedAttraction.cost }}</span>
              </div>
              <p v-if="selectedAttraction.research_source" class="detail-source">来自公开攻略候选景点匹配</p>
            </div>
          </section>
        </section>

        <section class="panel wide-panel">
          <div class="panel-title">
            <h3>公开旅行攻略洞察</h3>
            <span>{{ researchStatusText }}</span>
          </div>
          <div v-if="hasResearchInsights" class="research-layout">
            <div class="research-notes">
              <article v-for="note in researchNotes" :key="note.url || note.title" class="research-note">
                <strong>{{ note.title || "公开旅行攻略" }}</strong>
                <p>{{ note.summary || "暂无摘要" }}</p>
                <a v-if="note.url" :href="note.url" target="_blank" rel="noreferrer">查看原笔记</a>
              </article>
            </div>
            <div class="research-insights">
              <article v-for="row in researchInsightRows" :key="row.label">
                <span>{{ row.label }}</span>
                <ul>
                  <li v-for="item in row.items" :key="item">{{ item }}</li>
                </ul>
              </article>
            </div>
          </div>
          <div v-else class="empty-state">{{ researchEmptyText }}</div>
        </section>
        <section class="panel wide-panel weather-overview-panel">
          <div class="panel-title">
            <h3>天气总览</h3>
            <span>{{ weatherStatusText }}</span>
          </div>
          <div v-if="weatherDisplayDays.length" class="weather-overview-grid">
            <article v-for="(item, index) in weatherDisplayDays" :key="item.date || index" class="weather-overview-card" :class="{ unavailable: item.unavailable }">
              <strong>Day {{ index + 1 }}</strong>
              <span>{{ item.city || "天气" }} · {{ item.date || "日期待确认" }}</span>
              <b>{{ item.unavailable ? "暂无预报" : (item.day_weather || item.weather || "待确认") }}</b>
              <em>{{ item.temp_min ?? "--" }}~{{ item.temp_max ?? "--" }}°C</em>
              <small>{{ item.unavailable ? weatherAvailabilityText(item) : `风力 ${item.wind_scale ?? "--"}` }}</small>
            </article>
          </div>
          <div v-else class="empty-state">生成规划后会在这里显示真实天气预报；未配置 OpenWeather 时不会编造天气。</div>
        </section>
      </section>

      <section v-show="activeTab === 'map'" class="map-layout">
        <section class="panel map-panel">
          <div class="panel-title">
            <h3>地图与路线</h3>
            <div class="map-tools">
              <select v-model="mapKeyword" @change="refreshPois">
                <option value="景点">景点</option>
                <option value="餐厅">餐厅</option>
                <option value="酒店">酒店</option>
                <option value="博物馆">博物馆</option>
              </select>
              <select v-model="mapView" @change="refreshMapImage">
                <option value="city">城市概览</option>
                <option value="poi">地点周边</option>
              </select>
            </div>
          </div>
          <div
            class="interactive-map"
            :class="{ dragging: mapDragging }"
            @wheel="zoomMap"
            @pointerdown="startMapPan"
            @pointermove="panMap"
            @pointerup="stopMapPan"
            @pointercancel="stopMapPan"
            @pointerleave="stopMapPan"
          >
            <div class="map-viewport" :class="{ 'amap-ready': amapReady }" :style="mapViewportStyle">
              <div ref="amapEl" class="amap-map"></div>
              <img
                v-if="mapImage && !mapImageError"
                :src="mapImage"
                alt="地图底图"
                draggable="false"
                @load="handleMapImageLoad"
                @error="handleMapImageError"
              />
              <div v-else-if="mapImageError" class="map-image-error">
                <MapPinned :size="24" />
                <span>地图底图加载失败</span>
                <button type="button" class="secondary-button" @click.stop="retryMapImage">重新加载</button>
              </div>
              <div v-else class="empty-state">正在加载地图底图。</div>
            </div>
            <div class="map-controls" @pointerdown.stop>
              <button type="button" class="map-control-button" title="放大地图" @click="changeMapZoom(0.2)">
                <ZoomIn :size="17" />
              </button>
              <button type="button" class="map-control-button" title="缩小地图" @click="changeMapZoom(-0.2)">
                <ZoomOut :size="17" />
              </button>
              <button type="button" class="map-control-button" title="重置地图视野" @click="resetMapView">
                <LocateFixed :size="17" />
              </button>
            </div>
            <span class="map-zoom-label">{{ Math.round(mapScale * 100) }}%</span>
            <span v-if="hasMultipleCities" class="map-city-label">多城市路线 · {{ cityCount }} 个城市</span>
          </div>
          <div class="route-box">
            <button type="button" class="secondary-button" :disabled="selectedPois.length !== 2" @click="estimateSelectedRoute">
              <Route :size="16" />
              估算路径
            </button>
            <p>{{ routeText }}</p>
          </div>
        </section>

        <section class="panel">
          <div class="panel-title">
            <h3>真实地点</h3>
            <span>{{ currentPois.length }} 个候选</span>
          </div>
          <ol class="poi-list">
            <li
              v-for="(poi, index) in currentPois"
              :key="`${poi.id || index}-${poi.name}`"
              :class="{ selected: selectedPoiIndexes.includes(index), highlighted: isHighlightedPoi(poi) }"
              @click="togglePoi(index)"
            >
              <span>{{ index + 1 }}</span>
              <div>
                <b>{{ poi.name || "未知地点" }}</b>
                <p>{{ poi.address || poi.type || "暂无详情" }}</p>
              </div>
            </li>
          </ol>
        </section>
      </section>

      <section v-show="activeTab === 'budget'" class="content-grid">
        <section class="panel">
          <div class="panel-title">
            <h3>预算拆分</h3>
            <span>{{ budgetTotal }}</span>
          </div>
          <ul class="budget-list">
            <li v-for="item in budgetRows" :key="item.label">
              <span>{{ item.label }}</span>
              <input v-model.number="editableBudget[item.key]" class="budget-input" type="number" min="0" step="10" :aria-label="item.label" />
            </li>
          </ul>
          <div class="budget-edit-footer">
            <span>调整后合计：{{ editedBudgetTotal }} 元</span>
            <button type="button" class="secondary-button" @click="applyBudgetEdit">应用预算</button>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">
            <h3>约束检查</h3>
            <span>{{ conflictLabel }}</span>
          </div>
          <ul class="plain-list">
            <li v-for="item in constraintMessages" :key="item">{{ item }}</li>
          </ul>
        </section>
        <section class="panel wide-panel">
          <div class="panel-title">
            <h3>天气与穿搭</h3>
            <span>{{ planDays }} 天行程 · 已获取 {{ weatherAvailableDays.length }} 天天气</span>
          </div>
          <div class="weather-grid">
            <p class="weather-status" :class="{ unavailable: Boolean(structuredPlan && !weatherAvailableDays.length) }">
              {{ weatherStatusText }}
            </p>
            <article v-for="(item, index) in weatherDisplayDays" :key="item.date || index" class="weather-card" :class="{ unavailable: item.unavailable }">
              <strong>Day {{ index + 1 }}</strong>
              <p>{{ item.unavailable ? "暂无预报" : (outfitDays[index]?.weather || weatherLabel(index + 1)) }}</p>
              <span>{{ outfitDays[index]?.outfit || (item.unavailable ? "该日期暂未进入 OpenWeather 可查询窗口。" : "按当天温度和行程安排准备衣物。") }}</span>
            </article>
          </div>
        </section>
      </section>

      <section v-show="activeTab === 'graph'" class="panel graph-panel">
        <div class="panel-title">
          <h3>知识图谱</h3>
          <span>{{ graphNodeCount }} 节点 / {{ graphEdgeCount }} 关系</span>
        </div>
        <div ref="graphEl" class="graph-canvas"></div>
      </section>

      <section v-show="activeTab === 'raw'" class="panel raw-panel">
        <div class="panel-title">
          <h3>原始方案</h3>
          <span>{{ job?.step_count || 0 }} 条记录</span>
        </div>
        <pre>{{ job?.content || "规划完成后会显示可导出的 Markdown 内容。" }}</pre>
      </section>
    </section>

    <div v-if="settingsOpen" class="modal-backdrop" @click.self="settingsOpen = false">
      <section class="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <div class="panel-title">
          <div>
            <p class="eyebrow">RUNTIME SETTINGS</p>
            <h3 id="settings-title">接口与服务设置</h3>
          </div>
          <button type="button" class="icon-button" title="关闭设置" @click="settingsOpen = false">
            <X :size="17" />
          </button>
        </div>
        <p class="settings-note">密钥只写入本机后端的 runtime_settings.json；留空表示保持当前配置。</p>
        <label>后端地址<input v-model.trim="settingsForm.api_base_url" placeholder="http://127.0.0.1:8010" /></label>
        <label>LLM Base URL<input v-model.trim="settingsForm.LLM_BASE_URL" placeholder="https://.../v1" /></label>
        <label>LLM 模型<input v-model.trim="settingsForm.LLM_MODEL_ID" placeholder="模型名称" /></label>
        <label>LLM API Key<input v-model.trim="settingsForm.LLM_API_KEY" type="password" placeholder="留空保持已配置密钥" /></label>
        <label>OpenWeather API Key<input v-model.trim="settingsForm.OPENWEATHER_API_KEY" type="password" placeholder="留空保持已配置密钥" /></label>
        <label>Tavily API Key<input v-model.trim="settingsForm.TAVILY_API_KEY" type="password" placeholder="留空保持已配置 Key" /></label>
        <label>Tavily 限定域名<input v-model.trim="settingsForm.TAVILY_INCLUDE_DOMAINS" placeholder="例如 dianping.com,mafengwo.cn,qyer.com" /></label>
        <div class="settings-status">
          <span>高德服务 Key：{{ settingsStatus?.has_amap_service_key ? "已配置" : "未配置" }}</span>
          <span>天气 Key：{{ settingsStatus?.has_openweather_api_key ? "已配置" : "未配置" }}</span>
          <span>LLM Key：{{ settingsStatus?.has_llm_api_key ? "已配置" : "未配置" }}</span>
          <span>Tavily：{{ settingsStatus?.has_tavily_api_key ? "已配置" : "未配置" }}</span>
        </div>
        <p v-if="settingsError" class="planner-error">{{ settingsError }}</p>
        <div class="settings-actions">
          <button type="button" class="secondary-button" @click="settingsOpen = false">取消</button>
          <button type="button" class="primary-button settings-save-button" :disabled="settingsSaving" @click="saveSettings">
            <Save :size="16" />
            {{ settingsSaving ? "保存中" : "保存设置" }}
          </button>
        </div>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import * as echarts from "echarts";
import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ArrowDown, ArrowUp, CalendarDays, Download, FileDown, Info, LocateFixed, MapPinned, Network, Plus, RefreshCw, Route, Save, Settings, Trash2, WalletCards, WandSparkles, X, ZoomIn, ZoomOut } from "lucide-vue-next";
import { fetchAttractionPhoto, fetchPois, fetchRoute, fetchRuntimeSettings, geocode, getApiBase, getTripJob, healthCheck, saveRuntimeSettings, setApiBase, startTripPlan, staticMapUrl } from "./services/api";
import type { CitySegment, ItineraryAttraction, ItineraryDay, Poi, TripForm, TripJob } from "./types/trip";
import type { RuntimeSettingsStatus } from "./services/api";

type TabKey = "overview" | "map" | "budget" | "graph" | "raw";

const graphCategoryLabels: Record<string, string> = {
  city: "城市",
  day: "行程日",
  attraction: "景点",
  restaurant: "餐饮",
  hotel: "住宿",
  weather: "天气",
  budget: "预算",
  constraint: "约束",
  packing: "行李",
  research: "攻略洞察",
};

const graphCategoryColors: Record<string, string> = {
  city: "#0f766e",
  day: "#2563eb",
  attraction: "#d97706",
  restaurant: "#e11d48",
  hotel: "#7c3aed",
  weather: "#0284c7",
  budget: "#dc2626",
  constraint: "#9333ea",
  packing: "#059669",
  research: "#c2410c",
};

const graphEdgeLabels: Record<string, string> = {
  route: "路线",
  itinerary: "行程",
  weather: "天气",
  visit: "游览",
  next: "下一站",
  food: "餐饮",
  stay: "住宿",
  budget: "预算",
  constraint: "约束",
  pack: "行李",
  research: "攻略",
};

const form = reactive<TripForm>({
  city: "",
  start_date: "",
  days: 1,
  travelers: 1,
  max_budget: 0,
  preferences: [],
  pace: "",
  accommodation: "",
  transportation: "",
  special_requirements: "",
  include_packing: false,
});

const tabs = [
  { key: "overview", label: "总览", icon: CalendarDays },
  { key: "map", label: "地图", icon: MapPinned },
  { key: "budget", label: "预算", icon: WalletCards },
  { key: "graph", label: "图谱", icon: Network },
  { key: "raw", label: "原文", icon: Download },
] as const;

const backendOk = ref(false);
const activeTab = ref<TabKey>("overview");
const settingsOpen = ref(false);
const settingsSaving = ref(false);
const settingsError = ref("");
const settingsStatus = ref<RuntimeSettingsStatus | null>(null);
const settingsForm = reactive<Record<string, string>>({
  api_base_url: getApiBase(),
  LLM_BASE_URL: "",
  LLM_MODEL_ID: "",
  LLM_API_KEY: "",
  OPENWEATHER_API_KEY: "",
  TAVILY_API_KEY: "",
  TAVILY_INCLUDE_DOMAINS: "",
});
const preferenceText = ref(form.preferences.join(", "));
const job = ref<TripJob | null>(null);
const jobId = ref("");
const progress = ref(0);
const progressText = ref("填写需求后生成完整行程");
const plannerError = ref("");
const exportingPdf = ref(false);
const attractionPhotos = ref<Record<string, string>>({});
const selectedAttraction = ref<ItineraryAttraction | null>(null);
const additionalCities = ref<CitySegment[]>([]);
const editableBudget = reactive<Record<string, number>>({
  attractions: 0,
  meals: 0,
  hotels: 0,
  transportation: 0,
  misc: 0,
});
const currentPois = ref<Poi[]>([]);
const selectedPoiIndexes = ref<number[]>([]);
const mapKeyword = ref("景点");
const mapView = ref<"city" | "poi">("city");
const mapImage = ref("");
const mapImageReady = ref(false);
const mapImageError = ref(false);
let mapRetryCount = 0;
const amapEl = ref<HTMLDivElement | null>(null);
const amapReady = ref(false);
const amapError = ref("");
const mapScale = ref(1);
const mapOffset = reactive({ x: 0, y: 0 });
const mapDragging = ref(false);
let mapDragOrigin = { pointerX: 0, pointerY: 0, offsetX: 0, offsetY: 0 };
const routeText = ref("选择两个地点后点击估算路径。");
const highlightedPoiKey = ref("");
const graphSelectionText = ref("");
const graphEl = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;
let amapInstance: any = null;
let amapMarkers: any[] = [];
let polling = false;

const structuredPlan = computed(() => job.value?.structured_plan || null);
const knowledgeGraph = computed(() => job.value?.knowledge_graph || null);
const itineraryDays = computed<ItineraryDay[]>(() => structuredPlan.value?.itinerary_days || []);
const showcaseAttractions = computed(() =>
  itineraryDays.value
    .flatMap((day) => day.attractions.map((place) => ({ day: day.day, place })))
    .slice(0, 8)
);
const planCities = computed<CitySegment[]>(() => {
  const cities = structuredPlan.value?.cities;
  if (Array.isArray(cities) && cities.length) return cities as CitySegment[];
  if (form.city) return [{ city: structuredPlan.value?.city || form.city, days: Number(structuredPlan.value?.days_count || form.days || 1) }];
  return [];
});
const focusedShowcaseIndex = ref<number | null>(null);
const researchInsights = computed(() => structuredPlan.value?.travel_insights || {});
const researchNotes = computed(() => researchInsights.value?.notes || []);
const researchMerged = computed(() => researchInsights.value?.merged_insights || {});
const researchStatusText = computed(() => {
  if (!structuredPlan.value) return "等待规划结果";
  return researchInsights.value?.ok ? `${researchNotes.value.length} 条公开攻略` : "暂不可用";
});
const researchEmptyText = computed(() => researchInsights.value?.error || "生成规划后会显示公开旅行攻略提炼出的候选景点、避坑点和预约提醒。");
const researchInsightRows = computed(() => {
  const collect = (field: "candidate_attractions" | "pitfalls" | "reservation_tips") => {
    const mergedItems = Array.isArray(researchMerged.value?.[field]) ? researchMerged.value[field] : [];
    const noteItems = researchNotes.value.flatMap((note: any) => Array.isArray(note?.[field]) ? note[field] : []);
    return [...new Set([...mergedItems, ...noteItems].map((item) => String(item || "").trim()).filter(Boolean))].slice(0, 10);
  };
  return [
    { label: "候选景点", items: collect("candidate_attractions") },
    { label: "避坑点", items: collect("pitfalls") },
    { label: "预约提醒", items: collect("reservation_tips") },
  ].filter((row) => row.items.length);
});
const hasResearchInsights = computed(() => researchNotes.value.length > 0 || researchInsightRows.value.length > 0);
const weatherDays = computed(() => structuredPlan.value?.weather?.daily || []);
const weatherAvailableDays = computed(() => weatherDays.value.filter((item: any) => !item?.unavailable));
const weatherDisplayDays = computed(() => {
  if (!structuredPlan.value) return [];
  const totalDays = Math.max(Number(planDays.value) || 1, weatherDays.value.length);
  const startDate = structuredPlan.value?.start_date || form.start_date;
  return Array.from({ length: totalDays }, (_, index) => weatherDays.value[index] || {
    date: dateAfterDays(startDate, index),
    unavailable: true,
    day_weather: "",
    weather: "",
    temp_min: null,
    temp_max: null,
  });
});
const weatherStatusText = computed(() => {
  if (!structuredPlan.value) return "等待规划结果";
  const weather = structuredPlan.value.weather || {};
  if (weather.ok && weatherAvailableDays.value.length) {
    const totalDays = Math.max(Number(weather.requested_days) || Number(planDays.value) || weatherDays.value.length, weatherDays.value.length);
    const unavailableReason = weatherDays.value.some((item: any) => item?.unavailable && String(item?.error || "").includes("404"))
      ? "部分城市未找到天气数据"
      : "其余日期超出当前预报窗口";
    return weatherAvailableDays.value.length < totalDays
      ? `OpenWeather 已获取 ${weatherAvailableDays.value.length}/${totalDays} 天 · ${unavailableReason}`
      : `OpenWeather 实时预报 · ${weatherAvailableDays.value.length} 天`;
  }
  const windowText = weather.available_from && weather.available_until
    ? `可查询窗口：${weather.available_from} 至 ${weather.available_until}`
    : "";
  const totalDays = Math.max(Number(weather.requested_days) || Number(planDays.value) || 1, weatherDays.value.length);
  return [weather.error, windowText].filter(Boolean).join(" · ") || `当前暂无可用天气预报 · 0/${totalDays} 天`;
});
const outfitDays = computed(() => structuredPlan.value?.packing?.onion_layering_calendar || []);
const isRunning = computed(() => ["queued", "running", "cancelling"].includes(job.value?.status || ""));
const selectedPois = computed(() => selectedPoiIndexes.value.map((index) => currentPois.value[index]).filter(Boolean));
const mapPoints = computed(() => currentPois.value.map((poi) => poiLocationString(poi)).filter(Boolean).join("|"));
const cityCount = computed(() => structuredPlan.value?.cities?.length || 0);
const hasMultipleCities = computed(() => cityCount.value > 1);
const mapViewportStyle = computed(() => ({
  transform: amapReady.value ? "none" : `translate3d(${mapOffset.x}px, ${mapOffset.y}px, 0) scale(${mapScale.value})`,
}));
const requestedTotalDays = computed(() => form.days + additionalCities.value.reduce((sum, item) => sum + Math.max(1, Number(item.days) || 1), 0));
const planDays = computed(() => structuredPlan.value?.days_count || requestedTotalDays.value);
const planTitle = computed(() => structuredPlan.value ? `${structuredPlan.value.city} ${structuredPlan.value.days_count} 天游` : "等待生成旅行方案");
const graphNodeCount = computed(() => knowledgeGraph.value?.nodes?.length || 0);
const graphEdgeCount = computed(() => knowledgeGraph.value?.edges?.length || 0);
const budgetTotal = computed(() => {
  if (!structuredPlan.value) return "待计算";
  return `${editedBudgetTotal.value} 元`;
});
const editedBudgetTotal = computed(() => Object.values(editableBudget).reduce((sum, value) => sum + (Number(value) || 0), 0).toFixed(2).replace(/\.00$/, ""));
const conflictLabel = computed(() => structuredPlan.value?.constraints?.has_conflicts ? "需要调整" : "未发现明显冲突");
const constraintMessages = computed(() => {
  const constraints = structuredPlan.value?.constraints || {};
  const suggestions = constraints.suggestions || [];
  if (Array.isArray(suggestions) && suggestions.length) return suggestions;
  return [conflictLabel.value, "普通情况走快速链路；预算、路线或天气异常时再进入重规划。"];
});
const budgetRows = computed(() => {
  const breakdown = structuredPlan.value?.budget?.breakdown || {};
  const labels: Record<string, string> = {
    attractions: "门票/活动",
    meals: "餐饮",
    hotels: "住宿",
    transportation: "市内交通",
    misc: "弹性预留",
  };
  return Object.entries(labels).map(([key, label]) => ({
    key,
    label,
    value: `${editableBudget[key] ?? breakdown[key] ?? 0} 元`,
  }));
});

watch(preferenceText, (value) => {
  form.preferences = value.split(/[,，、\n]/).map((item) => item.trim()).filter(Boolean);
});

watch(knowledgeGraph, () => {
  if (activeTab.value === "graph") {
    void renderGraph();
  }
});

watch(activeTab, (value) => {
  if (value === "graph") {
    void renderGraph();
  }
  if (value === "map") {
    void renderInteractiveMap();
  }
});

onMounted(async () => {
  try {
    const health = await healthCheck();
    backendOk.value = health.status === "ok";
  } catch {
    backendOk.value = false;
  }
  await loadSettings();
  await refreshPois();
  window.addEventListener("resize", resizeGraph);
});

async function loadSettings() {
  try {
    const response = await fetchRuntimeSettings();
    settingsStatus.value = response.data;
  } catch {
    settingsStatus.value = null;
  }
}

function openSettings() {
  settingsForm.api_base_url = getApiBase();
  settingsError.value = "";
  settingsOpen.value = true;
  void loadSettings();
}

async function saveSettings() {
  settingsSaving.value = true;
  settingsError.value = "";
  try {
    const nextApiBase = setApiBase(settingsForm.api_base_url);
    const payload = Object.fromEntries(
      Object.entries(settingsForm).filter(([key, value]) => key !== "api_base_url" && value.trim())
    );
    const response = await saveRuntimeSettings(payload);
    settingsStatus.value = response.data;
    settingsOpen.value = false;
    backendOk.value = (await healthCheck()).status === "ok";
    if (nextApiBase !== getApiBase()) setApiBase(nextApiBase);
    await refreshPois();
  } catch (error: any) {
    settingsError.value = error?.message || "设置保存失败，请检查后端地址";
  } finally {
    settingsSaving.value = false;
  }
}

onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeGraph);
  chart?.dispose();
  amapInstance?.destroy?.();
});

async function submitPlan() {
  if (!form.city.trim()) {
    plannerError.value = "请先填写目的地。";
    return;
  }
  if (!form.start_date) {
    plannerError.value = "请先选择出发日期。";
    return;
  }
  job.value = null;
  jobId.value = "";
  plannerError.value = "";
  attractionPhotos.value = {};
  selectedAttraction.value = null;
  focusedShowcaseIndex.value = null;
  mapImageReady.value = false;
  mapImageError.value = false;
  mapRetryCount = 0;
  progress.value = 8;
  progressText.value = "任务已提交，正在准备工具链";
  try {
    const cities = [
      { city: form.city.trim(), days: Math.max(1, Number(form.days) || 1) },
      ...additionalCities.value
        .map((item) => ({ city: item.city.trim(), days: Math.max(1, Number(item.days) || 1) }))
        .filter((item) => item.city),
    ];
    const created = await startTripPlan({
      ...form,
      days: cities.reduce((sum, item) => sum + item.days, 0),
      cities: cities.length > 1 ? cities : undefined,
    });
    jobId.value = created.job_id;
    polling = true;
    await pollJob(created.job_id);
  } catch (error: any) {
    polling = false;
    progress.value = 0;
    progressText.value = "规划失败";
    plannerError.value = error?.message || "无法连接规划服务，请确认后端 8010 端口已启动。";
  }
}

async function pollJob(id: string) {
  while (polling) {
    const nextJob = await getTripJob(id);
    job.value = nextJob;
    progress.value = nextJob.progress ?? (nextJob.status === "completed" ? 100 : Math.min(95, 12 + (nextJob.step_count || 0) * 9));
    progressText.value = nextJob.status === "completed" ? "规划完成" : nextJob.stage || progressMessage(nextJob);
    if (nextJob.status === "completed") {
      polling = false;
      syncBudgetEditor();
      await usePlanPois();
      await refreshMapImage();
      void loadAttractionPhotos();
      if (activeTab.value === "graph") {
        await renderGraph();
      }
      return;
    }
    if (["failed", "cancelled"].includes(nextJob.status)) {
      polling = false;
      progressText.value = nextJob.error || "规划任务未完成";
      return;
    }
    await sleep(700);
  }
}

function attractionPhotoKey(place: Poi): string {
  return `${form.city}::${place.name || ""}`;
}

function attractionPhoto(place: Poi): string {
  return attractionPhotos.value[attractionPhotoKey(place)] || place.photo_url || "";
}

function handleAttractionImageError(place: Poi) {
  delete attractionPhotos.value[attractionPhotoKey(place)];
}

async function loadAttractionPhotos() {
  const uniquePlaces = Array.from(
    new Map(
      itineraryDays.value
        .flatMap((day) => day.attractions)
        .filter((place) => place.name)
        .map((place) => [attractionPhotoKey(place), place])
    ).values()
  );
  let cursor = 0;
  const worker = async () => {
    while (cursor < uniquePlaces.length) {
      const place = uniquePlaces[cursor++];
      const key = attractionPhotoKey(place);
      if (attractionPhotos.value[key] || place.photo_url) continue;
      try {
        const result = await fetchAttractionPhoto(place.name || "", form.city);
        if (result?.ok && result.photo_url) {
          attractionPhotos.value[key] = result.photo_url;
        }
      } catch {
        // Missing images must not block the generated itinerary.
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(3, uniquePlaces.length) }, () => worker()));
}

function addCityStop() {
  additionalCities.value.push({ city: "", days: 1 });
}

function removeCityStop(index: number) {
  additionalCities.value.splice(index, 1);
}

function openAttractionDetails(place: ItineraryAttraction) {
  selectedAttraction.value = place;
}

function syncBudgetEditor() {
  const breakdown = structuredPlan.value?.budget?.breakdown || {};
  for (const key of Object.keys(editableBudget)) {
    editableBudget[key] = Number(breakdown[key] || 0);
  }
}

function applyBudgetEdit() {
  const budget = structuredPlan.value?.budget;
  if (!budget) return;
  budget.breakdown = { ...(budget.breakdown || {}), ...editableBudget };
  budget.total = Number(editedBudgetTotal.value);
  if (structuredPlan.value.budget_check) {
    structuredPlan.value.budget_check.over_budget = Boolean(form.max_budget && budget.total > form.max_budget);
  }
}

function moveAttraction(dayNumber: number, index: number, direction: -1 | 1) {
  const day = itineraryDays.value.find((item) => item.day === dayNumber);
  if (!day) return;
  const targetIndex = index + direction;
  if (targetIndex < 0 || targetIndex >= day.attractions.length) return;
  [day.attractions[index], day.attractions[targetIndex]] = [day.attractions[targetIndex], day.attractions[index]];
}

async function recalculateDayRoutes(day: ItineraryDay) {
  const results: string[] = [];
  for (let index = 1; index < day.attractions.length; index += 1) {
    const origin = day.attractions[index - 1];
    const destination = day.attractions[index];
    const originLocation = poiLocationString(origin);
    const destinationLocation = poiLocationString(destination);
    if (!originLocation || !destinationLocation) continue;
    const result = await fetchRoute(originLocation, destinationLocation, form.city, routeMode());
    if (result.ok) {
      destination.transfer_minutes = Math.round(Number(result.duration_minutes || 0));
      results.push(`${origin.name} -> ${destination.name} ${result.duration_minutes || 0} 分钟`);
    }
  }
  routeText.value = results.length ? `Day ${day.day}：${results.join("；")}` : "当前景点缺少坐标，暂时无法重算路线。";
}

async function refreshPois() {
  if (!form.city.trim()) {
    currentPois.value = [];
    mapImage.value = "";
    return;
  }
  routeText.value = "选择两个地点后点击估算路径。";
  selectedPoiIndexes.value = [];
  highlightedPoiKey.value = "";
  graphSelectionText.value = "";
  try {
    const data = await fetchPois(form.city, mapKeyword.value);
    currentPois.value = data.pois || [];
    await refreshMapImage();
    if (activeTab.value === "map") await renderInteractiveMap();
  } catch {
    currentPois.value = [];
    mapImage.value = "";
    routeText.value = "地点服务暂时不可用，请确认后端已启动后重试。";
  }
}

async function usePlanPois() {
  const planPois = structuredPlan.value?.attractions || [];
  if (planPois.length) {
    currentPois.value = planPois;
    if (activeTab.value === "map") await renderInteractiveMap();
    mapKeyword.value = "景点";
  } else {
    await refreshPois();
  }
}

async function renderInteractiveMap() {
  await nextTick();
  if (!amapEl.value || !currentPois.value.length) return;
  // Use the backend static map as the source of truth. The browser JS API can
  // report a successful initialization while its tiles remain blank when the
  // security configuration is incomplete. The static image still supports
  // reliable pan and zoom through the viewport transform below.
  amapReady.value = false;
  amapError.value = "";
  amapInstance?.destroy?.();
  amapInstance = null;
  amapMarkers = [];
  await refreshMapImage();
}

async function refreshMapImage() {
  if (amapReady.value && amapInstance) {
    if (mapView.value === "poi" && selectedPois.value[0]) {
      const location = poiLocationString(selectedPois.value[0]);
      if (location) {
        const [lng, lat] = location.split(",").map(Number);
        amapInstance.setZoomAndCenter(15, [lng, lat]);
      }
    } else if (amapMarkers.length) {
      amapInstance.setFitView(amapMarkers, false, [54, 54, 54, 54]);
    }
    return;
  }
  let center = "";
  let zoom = 10;
  if (mapView.value === "city" && mapPoints.value) {
    center = averageCenter(currentPois.value);
    zoom = hasMultipleCities.value ? 5 : 10;
  } else if (mapView.value === "city") {
    const result = await geocode(form.city, form.city).catch(() => null);
    const location = result?.location || {};
    if (location.longitude && location.latitude) {
      center = `${location.longitude},${location.latitude}`;
      zoom = 10;
    }
  } else {
    const average = averageCenter(currentPois.value);
    if (average) {
      center = average;
      zoom = 12;
    }
  }
  resetMapView();
  mapImageReady.value = false;
  mapImageError.value = false;
  mapRetryCount = 0;
  mapImage.value = staticMapUrl(form.city, mapKeyword.value, center, zoom, mapPoints.value);
}

function handleMapImageLoad() {
  mapImageReady.value = true;
  mapImageError.value = false;
  mapRetryCount = 0;
}

function handleMapImageError() {
  mapImageReady.value = false;
  if (mapRetryCount < 1) {
    mapRetryCount += 1;
    window.setTimeout(() => {
      mapImageError.value = false;
      mapImage.value = staticMapUrl(form.city, mapKeyword.value, averageCenter(currentPois.value), hasMultipleCities.value ? 5 : 10, mapPoints.value);
    }, 300);
    return;
  }
  mapImageError.value = true;
}

function retryMapImage() {
  mapRetryCount = 0;
  mapImageError.value = false;
  mapImageReady.value = false;
  void refreshMapImage();
}

function changeMapZoom(delta: number) {
  if (amapReady.value && amapInstance) {
    const zoom = Number(amapInstance.getZoom?.() || 11);
    amapInstance.setZoom(Math.min(20, Math.max(3, zoom + delta * 5)));
    return;
  }
  mapScale.value = Math.min(2.5, Math.max(1, Number((mapScale.value + delta).toFixed(2))));
  if (mapScale.value === 1) resetMapView();
}

function zoomMap(event: WheelEvent) {
  changeMapZoom(event.deltaY < 0 ? 0.15 : -0.15);
}

function startMapPan(event: PointerEvent) {
  if (event.button !== 0 || mapScale.value <= 1) return;
  mapDragging.value = true;
  mapDragOrigin = {
    pointerX: event.clientX,
    pointerY: event.clientY,
    offsetX: mapOffset.x,
    offsetY: mapOffset.y,
  };
  (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
}

function panMap(event: PointerEvent) {
  if (!mapDragging.value) return;
  mapOffset.x = mapDragOrigin.offsetX + event.clientX - mapDragOrigin.pointerX;
  mapOffset.y = mapDragOrigin.offsetY + event.clientY - mapDragOrigin.pointerY;
}

function stopMapPan(event?: PointerEvent) {
  if (!mapDragging.value) return;
  mapDragging.value = false;
  if (event) (event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId);
}

function resetMapView() {
  if (amapReady.value && amapInstance && amapMarkers.length) {
    amapInstance.setFitView(amapMarkers, false, [54, 54, 54, 54]);
    return;
  }
  mapScale.value = 1;
  mapOffset.x = 0;
  mapOffset.y = 0;
}

function togglePoi(index: number) {
  if (!poiLocationString(currentPois.value[index])) return;
  if (selectedPoiIndexes.value.includes(index)) {
    selectedPoiIndexes.value = selectedPoiIndexes.value.filter((item) => item !== index);
  } else {
    selectedPoiIndexes.value = [...selectedPoiIndexes.value, index].slice(-2);
  }
}

async function estimateSelectedRoute() {
  if (selectedPois.value.length !== 2) return;
  const [origin, destination] = selectedPois.value;
  const result = await fetchRoute(poiLocationString(origin), poiLocationString(destination), form.city, routeMode());
  if (!result.ok) {
    routeText.value = result.error || "路径估算失败";
    return;
  }
  routeText.value = `${origin.name} -> ${destination.name}，约 ${(Number(result.distance_meters || 0) / 1000).toFixed(1)} 公里，${result.duration_minutes || 0} 分钟。`;
}

async function handleGraphClick(params: any) {
  const node = params?.data || {};
  if (node.node_type !== "attraction") return;
  await focusPoi({
    name: node.name,
    address: node.address,
    location: node.location,
  });
}

async function focusPoiFromItinerary(poi: Poi) {
  await focusPoi(poi);
}

async function selectShowcaseAttraction(index: number, poi: Poi) {
  await focusPoiFromItinerary(poi);
}

async function focusPoi(poi: Poi) {
  const key = poiKey(poi);
  if (!key) return;
  highlightedPoiKey.value = key;
  graphSelectionText.value = poi.name ? `已定位：${poi.name}` : "";
  routeText.value = graphSelectionText.value || routeText.value;

  const planPois = structuredPlan.value?.attractions || [];
  if (planPois.length && findPoiIndex(currentPois.value, poi) < 0) {
    currentPois.value = planPois;
  }

  const index = findPoiIndex(currentPois.value, poi);
  selectedPoiIndexes.value = index >= 0 ? [index] : [];
  mapKeyword.value = poi.name || mapKeyword.value;
  mapView.value = "poi";
  activeTab.value = "map";

  const center = poiLocationString(poi);
  if (amapReady.value && amapInstance && center) {
    const [lng, lat] = center.split(",").map(Number);
    amapInstance.setZoomAndCenter(15, [lng, lat]);
    return;
  }
  mapImage.value = staticMapUrl(form.city, poi.name || mapKeyword.value, center, center ? 15 : 12, mapPoints.value);
}

async function renderGraph() {
  await nextTick();
  if (!graphEl.value || !knowledgeGraph.value) return;
  chart = chart || echarts.init(graphEl.value);
  const graphCategories = (knowledgeGraph.value.categories || []).map((item: any) => ({
    ...item,
    name: graphCategoryLabels[item.name] || item.name,
    itemStyle: { color: graphCategoryColors[item.name] || "#64748b" },
  }));
  const graphNodes = (knowledgeGraph.value.nodes || []).map((node: any) => {
    let name = String(node.name || "未命名");
    const dayMatch = name.match(/^Day\s+(\d+)$/i);
    if (dayMatch) name = `第 ${dayMatch[1]} 天`;
    if (name === "Packing checklist") name = "行李清单";
    if (name === "Travel insights") name = "攻略洞察";
    if (name === "Travel research unavailable") name = "攻略暂不可用";
    if (name.startsWith("Budget ")) name = name.replace(/^Budget\s+/, "预算 ");
    if (name.startsWith("Constraints:")) name = name.replace(/^Constraints:/, "约束：");
    return { ...node, name };
  });
  chart.setOption({
    tooltip: {
      backgroundColor: "#ffffff",
      borderColor: "#dbe5e4",
      borderWidth: 1,
      textStyle: { color: "#172536", fontSize: 12 },
      formatter: (params: any) => {
        const data = params.data || {};
        const category = graphCategories[Number(data.category)]?.name || "节点";
        const detail = String(data.value || "").trim();
        return detail
          ? `${category} · ${data.name || "未命名"}<br/><span style="color:#71818d">${detail}</span>`
          : `${category} · ${data.name || "未命名"}`;
      },
    },
    legend: [{
      bottom: 8,
      left: "center",
      type: "scroll",
      data: graphCategories.map((item: any) => item.name),
      itemWidth: 12,
      itemHeight: 12,
      itemGap: 14,
      textStyle: { color: "#526475", fontSize: 12 },
    }],
    series: [{
      type: "graph",
      layout: "force",
      roam: true,
      draggable: true,
      categories: graphCategories,
      data: graphNodes,
      links: (knowledgeGraph.value.edges || []).map((edge: any) => ({
        source: edge.source,
        target: edge.target,
        label: {
          show: Boolean(edge.label),
          formatter: graphEdgeLabels[edge.label] || edge.label,
          color: "#71818d",
          fontSize: 10,
        },
      })),
      edgeSymbol: ["none", "arrow"],
      edgeSymbolSize: 7,
      force: { repulsion: 260, edgeLength: [100, 160], gravity: 0.08, friction: 0.12 },
      label: {
        show: true,
        position: "right",
        color: "#334155",
        fontSize: 12,
        backgroundColor: "rgba(255,255,255,0.9)",
        borderColor: "#e2e8f0",
        borderWidth: 1,
        borderRadius: 4,
        padding: [3, 5],
      },
      lineStyle: { color: "#94a3b8", curveness: 0.16, opacity: 0.58 },
      emphasis: {
        focus: "adjacency",
        scale: 1.18,
        lineStyle: { width: 2.5, opacity: 0.9 },
      },
      animationDuration: 500,
      animationDurationUpdate: 650,
    }],
  });
  chart.off("click");
  chart.on("click", (params: any) => {
    void handleGraphClick(params);
  });
  chart.resize();
}

function resizeGraph() {
  chart?.resize();
}

function progressMessage(nextJob: TripJob) {
  if (nextJob.status === "completed") return "规划完成";
  if (nextJob.status === "failed") return nextJob.error || "规划失败";
  const last = nextJob.steps?.[nextJob.steps.length - 1];
  const tool = last?.tool_name || "";
  const labels: Record<string, string> = {
    search_poi: "正在检索真实地点",
    get_weather_forecast: "正在读取天气趋势",
    estimate_route: "正在估算路线耗时",
    estimate_trip_budget: "正在核算预算",
    check_itinerary_constraints: "正在检查约束",
    generate_packing_and_outfits: "正在生成行李与穿搭",
    search_travel_notes: "正在检索公开旅行攻略",
  };
  return labels[tool] || "正在生成旅行方案";
}

function weatherLabel(day: number) {
  const weather = weatherDisplayDays.value[day - 1];
  if (!weather || weather.unavailable) return "暂无预报";
  const desc = weather.day_weather || weather.weather || "";
  return `${desc || "天气待确认"} ${weather.temp_min ?? ""}-${weather.temp_max ?? ""}C`;
}

function weatherAvailabilityText(item: any) {
  const error = String(item?.error || "");
  if (error.includes("404")) return "城市未找到天气数据";
  if (error) return "暂无可用天气预报";
  return "超出当前预报窗口";
}

function dateAfterDays(value: unknown, offset: number) {
  const raw = String(value || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return "";
  const date = new Date(`${raw}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return "";
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

function attractionTime(index: number) {
  return ["09:00", "11:30", "14:30", "17:00"][index] || "18:30";
}

function routeMode() {
  return form.transportation === "walking first" ? "walking" : form.transportation === "taxi" ? "driving" : "transit";
}

function poiLocationString(poi?: Poi) {
  const lng = Number(poi?.location?.longitude);
  const lat = Number(poi?.location?.latitude);
  if (!Number.isFinite(lng) || !Number.isFinite(lat) || lng === 0 || lat === 0) return "";
  return `${lng},${lat}`;
}

function isHighlightedPoi(poi?: Poi) {
  return Boolean(highlightedPoiKey.value && poiKey(poi) === highlightedPoiKey.value);
}

function findPoiIndex(pois: Poi[], target: Poi) {
  const targetKey = poiKey(target);
  if (!targetKey) return -1;
  const exactIndex = pois.findIndex((poi) => poiKey(poi) === targetKey);
  if (exactIndex >= 0) return exactIndex;

  const targetName = normalizePoiText(target.name);
  const targetAddress = normalizePoiText(target.address);
  return pois.findIndex((poi) => {
    const sameName = normalizePoiText(poi.name) === targetName;
    const sameAddress = targetAddress && normalizePoiText(poi.address) === targetAddress;
    return sameName && (sameAddress || !targetAddress);
  });
}

function poiKey(poi?: Poi) {
  if (!poi) return "";
  const location = poiLocationString(poi);
  return [
    normalizePoiText(poi.name),
    normalizePoiText(poi.address),
    location,
  ].join("|");
}

function normalizePoiText(value: unknown) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, "");
}

function averageCenter(pois: Poi[]) {
  const points = pois
    .map((poi) => ({ lng: Number(poi.location?.longitude), lat: Number(poi.location?.latitude) }))
    .filter((item) => Number.isFinite(item.lng) && Number.isFinite(item.lat));
  if (!points.length) return "";
  const lng = points.reduce((sum, item) => sum + item.lng, 0) / points.length;
  const lat = points.reduce((sum, item) => sum + item.lat, 0) / points.length;
  return `${lng.toFixed(6)},${lat.toFixed(6)}`;
}

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function pdfPageHtml(content: string) {
  return `<div style="width:794px;min-height:1123px;box-sizing:border-box;padding:34px;background:#f4f7f9;color:#162333;font-family:Arial,'Microsoft YaHei','PingFang SC',sans-serif;">${content}</div>`;
}

function safeFilePart(value: string) {
  return value.replace(/[<>:"\/\\|?*\s]+/g, "-").replace(/^-+|-+$/g, "") || "trip-plan";
}

function buildPdfPages() {
  const plan = structuredPlan.value;
  if (!plan) return [];

  const cityRoute = planCities.value.map((segment) => segment.city).join(" -> ") || plan.city || form.city;
  const citySummary = planCities.value.map((segment) => `<span style="display:inline-block;margin:0 8px 8px 0;padding:6px 10px;border-radius:999px;background:#e6f5f2;color:#0f766e;font-size:12px;">${escapeHtml(segment.city)} · ${escapeHtml(segment.days)} 天</span>`).join("");
  const mapHtml = mapImageReady.value && mapImage.value
    ? `<section style="margin-top:18px;background:#fff;border-radius:12px;padding:12px;"><img src="${escapeHtml(mapImage.value)}" crossorigin="anonymous" style="display:block;width:100%;height:250px;object-fit:cover;border-radius:8px;" /></section>`
    : `<p style="margin:18px 0 0;color:#8b99a8;font-size:12px;">地图底图暂不可用，已保留完整景点地址和路线安排。</p>`;

  const budgetHtml = budgetRows.value.map((row) => `
    <div style="display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #edf1f5;font-size:13px;">
      <span>${escapeHtml(row.label)}</span><strong>${escapeHtml(row.value)}</strong>
    </div>`).join("");

  const pages = [pdfPageHtml(`
    <header style="padding:4px 2px 16px;border-bottom:3px solid #f47b59;">
      <div style="font-size:12px;letter-spacing:2px;color:#f47b59;font-weight:700;">TRIP PLAN</div>
      <h1 style="margin:8px 0 5px;font-size:30px;">${escapeHtml(cityRoute)} ${escapeHtml(plan.days_count || planDays.value)} 日游</h1>
      <div style="font-size:13px;color:#687789;">${escapeHtml(form.start_date)} · ${escapeHtml(form.travelers)} 位旅行者</div>
    </header>
    <section style="margin-top:18px;background:#fff;border-radius:12px;padding:18px 20px;"><h2 style="margin:0 0 10px;color:#0f766e;font-size:18px;">城市安排</h2>${citySummary || `<span>${escapeHtml(cityRoute)}</span>`}</section>
    ${mapHtml}
    <section style="margin-top:18px;background:#fff;border-radius:12px;padding:18px 20px;"><h2 style="margin:0 0 10px;color:#0f766e;font-size:18px;">预算概览</h2>${budgetHtml}<div style="display:flex;justify-content:space-between;padding-top:13px;font-size:16px;font-weight:700;"><span>预计总计</span><span style="color:#f47b59;">${escapeHtml(budgetTotal.value)}</span></div></section>
  `)];

  for (let index = 0; index < itineraryDays.value.length; index += 2) {
    const dayHtml = itineraryDays.value.slice(index, index + 2).map((day) => {
      const weather = weatherDisplayDays.value[Number(day.day) - 1] || (day as any).weather || {};
      return `<section style="margin-top:16px;background:#fff;border:1px solid #dce5ee;border-radius:12px;padding:18px 20px;">
        <div style="display:flex;justify-content:space-between;gap:16px;align-items:center;border-bottom:1px solid #edf1f5;padding-bottom:10px;">
          <h2 style="margin:0;color:#0f766e;font-size:20px;">Day ${escapeHtml(day.day)} · ${escapeHtml(day.city || form.city)}</h2>
          <span style="color:#687789;font-size:12px;">${escapeHtml(weather.day_weather || weather.weather || "天气待确认")} ${escapeHtml(weather.temp_min ?? "")}~${escapeHtml(weather.temp_max ?? "")}°C</span>
        </div>
        <p style="margin:12px 0;color:#687789;font-size:12px;">${escapeHtml(day.date || "日期待确认")} · ${escapeHtml(day.transportation || form.transportation || "交通待确认")} · ${escapeHtml(day.total_minutes || 0)} 分钟</p>
        ${(day.attractions || []).map((place, placeIndex) => `<div style="padding:11px 0;border-top:${placeIndex ? "1px solid #edf1f5" : "0"};"><div style="font-size:15px;font-weight:700;color:#162333;">${escapeHtml(placeIndex + 1)}. ${escapeHtml(place.name)}</div><div style="margin-top:5px;color:#687789;font-size:12px;">${escapeHtml(place.address || "地址待确认")} · 建议停留 ${escapeHtml(place.visit_minutes || 0)} 分钟</div></div>`).join("")}
        <p style="margin:10px 0 0;color:#516272;font-size:12px;">${escapeHtml(day.meals?.lunch?.name ? `午餐：${day.meals.lunch.name}` : "午餐：待安排")} · ${escapeHtml(day.meals?.dinner?.name ? `晚餐：${day.meals.dinner.name}` : "晚餐：待安排")} · ${escapeHtml(day.hotel?.name ? `住宿：${day.hotel.name}` : "住宿：待安排")}</p>
      </section>`;
    }).join("");
    pages.push(pdfPageHtml(`<h2 style="margin:0;color:#162333;font-size:22px;">每日行程</h2>${dayHtml}`));
  }

  const weatherHtml = weatherDisplayDays.value.length
    ? `<section style="margin-top:14px;background:#eef8f6;border-radius:12px;padding:16px 20px;"><h2 style="margin:0 0 10px;color:#0f766e;font-size:18px;">天气参考</h2>${weatherDisplayDays.value.map((day: any, index: number) => `<span style="display:inline-block;margin:0 8px 8px 0;padding:7px 10px;background:#fff;border-radius:8px;font-size:12px;">Day ${index + 1} ${escapeHtml(day.city || "")} ${escapeHtml(day.unavailable ? "暂无预报" : (day.day_weather || day.weather || "待确认"))} ${escapeHtml(day.temp_min ?? "")}~${escapeHtml(day.temp_max ?? "")}°C</span>`).join("")}</section>`
    : `<p style="color:#8b99a8;font-size:12px;">天气数据暂不可用，请以出行前最新预报为准。</p>`;
  const researchHtml = researchNotes.value.length
    ? `<section style="margin-top:14px;background:#fff8f4;border-radius:12px;padding:16px 20px;"><h2 style="margin:0 0 10px;color:#c65a3b;font-size:18px;">公开攻略参考</h2>${researchNotes.value.slice(0, 6).map((note: any) => `<div style="font-size:12px;margin:7px 0;"><strong>${escapeHtml(note.title || "公开攻略")}</strong>：${escapeHtml(note.summary || "")}</div>`).join("")}</section>`
    : "";
  pages.push(pdfPageHtml(`<h2 style="margin:0;color:#162333;font-size:22px;">出行参考</h2>${weatherHtml}${researchHtml}`));
  return pages;
}

async function downloadPdf() {
  if (!structuredPlan.value || exportingPdf.value) return;
  const plan = structuredPlan.value;
  exportingPdf.value = true;
  const exportContainer = document.createElement("div");
  exportContainer.style.position = "fixed";
  exportContainer.style.left = "-100000px";
  exportContainer.style.top = "0";
  exportContainer.style.width = "794px";
  document.body.appendChild(exportContainer);

  try {
    const pages = buildPdfPages();
    const pdf = new jsPDF({ orientation: "p", unit: "mm", format: "a4" });
    for (const [index, page] of pages.entries()) {
      exportContainer.innerHTML = page;
      const images = Array.from(exportContainer.querySelectorAll("img"));
      await Promise.all(images.map((image) => image.complete
        ? Promise.resolve()
        : new Promise<void>((resolve) => {
            image.onload = () => resolve();
            image.onerror = () => resolve();
          })));
      const canvas = await html2canvas(exportContainer, {
        backgroundColor: "#f4f7f9",
        scale: 2,
        useCORS: true,
        logging: false,
        windowWidth: 794,
      });
      if (index > 0) {
        pdf.addPage();
      }
      pdf.addImage(canvas.toDataURL("image/jpeg", 0.94), "JPEG", 0, 0, 210, 297);
    }
    const fileName = `${safeFilePart(planCities.value.map((segment) => segment.city).join("-"))}-${plan.days_count || planDays.value}日游.pdf`;
    pdf.save(fileName);
  } catch (error: any) {
    plannerError.value = `PDF 导出失败：${error?.message || "未知错误"}`;
  } finally {
    exportContainer.remove();
    exportingPdf.value = false;
  }
}

function downloadMarkdown() {
  if (!job.value?.content) return;
  const blob = new Blob([job.value.content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `trip-plan-${Date.now()}.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
</script>
